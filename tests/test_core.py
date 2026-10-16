import io
import json
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from legal_daily.commands import delivery_from_event, parse_command
from legal_daily.format import format_alerts, format_digest
from legal_daily.rss import parse_rss
from legal_daily.select import select_jobs, select_news
from legal_daily.sources import collect
from legal_daily.textutil import is_fresh, norm_link


class RssTest(unittest.TestCase):
    def test_cdata_item(self):
        xml = """
        <rss><channel>
          <item>
            <title><![CDATA[生成式人工智能服务管理暂行办法]]></title>
            <link>https://www.cac.gov.cn/a.htm</link>
            <pubDate>Wed, 08 Oct 2026 01:00:00 GMT</pubDate>
            <description><![CDATA[<p>网信办发布</p>]]></description>
          </item>
        </channel></rss>
        """
        items = parse_rss(xml)
        self.assertEqual(items[0]["title"], "生成式人工智能服务管理暂行办法")
        self.assertEqual(items[0]["link"], "https://www.cac.gov.cn/a.htm")
        self.assertIn("网信办发布", items[0]["snippet"])


class CommandTest(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(parse_command("你好"), {"type": "hello"})
        self.assertEqual(parse_command("@_user_1 展开第2条"), {"type": "expand_news", "n": 2})
        self.assertEqual(parse_command("展开 2"), {"type": "expand_news", "n": 2})
        self.assertEqual(parse_command("展开岗位 1"), {"type": "expand_job", "n": 1})
        self.assertEqual(parse_command("今天天气"), {"type": "help"})

    def test_delivery(self):
        event = {
            "event": {
                "message": {"chat_type": "p2p", "chat_id": "oc_1"},
                "sender": {"sender_id": {"open_id": "ou_abc"}},
            }
        }
        self.assertEqual(
            delivery_from_event(event),
            {"receive_id_type": "open_id", "receive_id": "ou_abc"},
        )


class SelectTest(unittest.TestCase):
    def test_drop_invented_link(self):
        allowed = {"https://www.cac.gov.cn/a.htm"}
        news = select_news(
            [
                {
                    "category": "新规",
                    "track": "合规",
                    "important": True,
                    "title_zh": "标识办法",
                    "title_en": "Labeling rules",
                    "one_line_zh": "要求对生成内容做标识",
                    "one_line_en": "Labels are required.",
                    "points": ["显式标识", ""],
                    "for_you": "面试可以讲标识义务",
                    "link": "https://www.cac.gov.cn/a.htm",
                },
                {
                    "title_zh": "编造的规章",
                    "one_line_zh": "不存在",
                    "link": "https://example.com/fake",
                },
            ],
            allowed,
        )
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["n"], 1)
        self.assertEqual(news[0]["points"], ["显式标识"])

    def test_recover_link_by_title(self):
        news = select_news(
            [
                {
                    "category": "新规",
                    "title_zh": "生成式人工智能服务管理暂行办法",
                    "one_line_zh": "网信办发布",
                    "link": "https://example.com/wrong",
                }
            ],
            {"https://www.cac.gov.cn/a.htm"},
            sources=[
                {
                    "title": "生成式人工智能服务管理暂行办法",
                    "link": "https://www.cac.gov.cn/a.htm",
                }
            ],
        )
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["link"], "https://www.cac.gov.cn/a.htm")

    def test_skip_seen_job(self):
        allowed = {"https://example.com/jobs/1", "https://example.com/jobs/2"}
        jobs = select_jobs(
            [
                {
                    "tier": "技术",
                    "employment": "实习",
                    "org": "幂律",
                    "role": "法律工程师",
                    "practice": "做合同审查产品",
                    "link": "https://example.com/jobs/1",
                },
                {
                    "tier": "复合",
                    "employment": "正式",
                    "org": "智合",
                    "role": "解决方案",
                    "practice": "把法律流程做成产品",
                    "link": "https://example.com/jobs/2",
                },
            ],
            allowed,
            seen_links=["https://example.com/jobs/1"],
        )
        self.assertEqual([job["org"] for job in jobs], ["智合"])
        self.assertEqual(jobs[0]["tier"], "复合")

    def test_source_experience_overrides_model(self):
        jobs = select_jobs(
            [
                {
                    "tier": "合规",
                    "employment": "正式",
                    "org": "腾讯",
                    "role": "法务",
                    "practice": "做数据合规",
                    "link": "https://join.qq.com/a",
                }
            ],
            {"https://join.qq.com/a"},
            [],
            sources=[
                {
                    "link": "https://join.qq.com/a",
                    "title": "腾讯｜法务",
                    "employment": "实习",
                    "experience": "应届",
                }
            ],
        )
        self.assertEqual(jobs[0]["employment"], "实习")
        self.assertEqual(jobs[0]["experience"], "应届")


class FormatTest(unittest.TestCase):
    def test_sections_and_empty_jobs(self):
        news = [
            {
                "n": 1,
                "category": "新规",
                "track": "合规",
                "important": True,
                "title_zh": "标识办法",
                "title_en": "Labeling rules",
                "one_line_zh": "要求标识",
                "one_line_en": "Labels are required.",
                "points": ["显式标识"],
                "for_you": "可以讲平台义务",
                "link": "https://www.cac.gov.cn/a.htm",
            }
        ]
        text = format_digest("2026-10-09", news, [])
        self.assertIn("【今日必读】", text)
        self.assertIn("【新规】", text)
        self.assertIn("今日无新岗位", text)
        self.assertIn("不构成法律意见", text)
        self.assertNotIn("检索到的新闻", text)
        alert = format_alerts(news, [])
        self.assertIn("重要变化", alert)
        self.assertIn("标识办法", alert)

    def test_lists_sources_when_selection_empty(self):
        text = format_digest(
            "2026-10-15",
            [],
            [],
            news_sources=[{"title": "网信办征求意见", "link": "https://www.cac.gov.cn/a.htm"}],
            job_sources=[{"title": "幂律招聘法律工程师", "link": "https://example.com/job"}],
        )
        self.assertNotIn("今日无重大更新", text)
        self.assertIn("网信办征求意见", text)
        self.assertIn("幂律招聘法律工程师", text)
        self.assertIn("https://www.cac.gov.cn/a.htm", text)

    def test_job_label_shows_experience(self):
        text = format_digest(
            "2026-10-15",
            [],
            [
                {
                    "n": 1,
                    "employment": "正式",
                    "experience": "应届",
                    "tier": "合规",
                    "org": "腾讯",
                    "role": "法务",
                    "city": "深圳",
                    "practice": "做合规",
                    "one_line_en": "Compliance.",
                    "link": "https://join.qq.com/a",
                }
            ],
        )
        self.assertIn("[正式·应届·合规]", text)


class SourceWindowTest(unittest.TestCase):
    def test_old_news_dropped(self):
        old = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%a, %d %b %Y %H:%M:%S GMT")

        def fetcher(url):
            link = "https://news.google.com/rss/articles/old" if "news.google" in url else "https://www.cac.gov.cn/new.htm"
            title = "人工智能新规"
            return f"""
            <rss><channel><item>
              <title>{title}</title>
              <link>{link}</link>
              <pubDate>{old if "news.google" in url else ""}</pubDate>
              <description>摘要</description>
            </item></channel></rss>
            """

        items = collect("news", ["人工智能"], 5, fetcher=fetcher)
        self.assertEqual(len(items), 1)
        self.assertIn("cac.gov.cn", items[0]["link"])

    def test_job_drops_shopping_pages(self):
        def fetcher(_url):
            return """
            <rss><channel>
              <item>
                <title>淘宝上大量所谓商场专柜剪标的衣服是高仿还是正品？</title>
                <link>https://www.zhihu.com/question/36609954</link>
                <description>知乎</description>
              </item>
              <item>
                <title>中国一重公开招聘法务合规人员</title>
                <link>https://www.sasac.gov.cn/a.htm</link>
                <description>面向社会招聘</description>
              </item>
            </channel></rss>
            """

        items = collect("job", ["数据合规 招聘"], 30, fetcher=fetcher)
        self.assertEqual([item["title"] for item in items], ["中国一重公开招聘法务合规人员"])

    def test_career_pages_keep_legal_titles(self):
        from legal_daily.careers import collect_career_jobs

        def fetcher(url, timeout=20, data=None, headers=None):
            if "join.qq.com" in url:
                return json.dumps(
                    {
                        "data": {
                            "positionList": [
                                {
                                    "positionTitle": "数据合规法务",
                                    "postId": "1",
                                    "workCities": "深圳",
                                    "recruitLabelName": "社招",
                                },
                                {"positionTitle": "后端工程师", "postId": "2", "workCities": "深圳"},
                            ]
                        }
                    }
                )
            if "careers.oppo.com" in url:
                return json.dumps(
                    {
                        "data": {
                            "records": [
                                {
                                    "idRecruitPosition": 9,
                                    "positionName": "法务经理",
                                    "recruitmentTypeName": "实习生",
                                    "positionDesc": "审核合同",
                                }
                            ]
                        }
                    }
                )
            if "didiglobal.com" in url:
                return json.dumps(
                    {"data": {"items": [{"jdId": 3, "jobName": "运营专家", "workArea": "北京", "jobDuty": "对接法务"}]}}
                )
            return "{}"

        rows = collect_career_jobs(fetcher)
        titles = [item["title"] for item in rows]
        self.assertIn("腾讯｜数据合规法务", titles)
        self.assertIn("OPPO｜法务经理", titles)
        self.assertNotIn("腾讯｜后端工程师", titles)
        self.assertFalse(any("运营专家" in title for title in titles))
        by_title = {item["title"]: item for item in rows}
        self.assertEqual(by_title["腾讯｜数据合规法务"]["experience"], "未写明")
        self.assertEqual(by_title["OPPO｜法务经理"]["employment"], "实习")
        self.assertEqual(by_title["OPPO｜法务经理"]["experience"], "应届")

    def test_drop_jobs_that_require_work_years(self):
        from legal_daily.careers import classify_opening

        self.assertIsNone(classify_opening("法务", "", "3年以上工作经验"))
        self.assertIsNone(classify_opening("法务", "", "1-3年"))
        self.assertIsNone(classify_opening("合规", "", "具备工作经验"))
        kept = classify_opening("法务", "", "5年以上经验优先")
        self.assertEqual(kept["experience"], "未写明")
        self.assertEqual(classify_opening("法务", "应届毕业生", "")["experience"], "应届")
        self.assertEqual(classify_opening("法务", "应届毕业生", "")["employment"], "正式")
        self.assertEqual(classify_opening("法务经理", "实习生", "审核合同")["employment"], "实习")
        self.assertEqual(classify_opening("法务", "", "0-3年")["experience"], "应届")
        self.assertEqual(classify_opening("法务", "", "经验不限")["experience"], "经验不限")

    def test_norm_link_strips_utm(self):
        self.assertEqual(
            norm_link("https://Example.com/a/?utm_source=rss&id=1"),
            "https://example.com/a?id=1",
        )
        self.assertTrue(is_fresh(None, 5))


class LlmRetryTest(unittest.TestCase):
    def test_retries_503_then_parses(self):
        from legal_daily.llm import complete_json

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                payload = {"choices": [{"message": {"content": "{\"ok\": true}"}}]}
                return json.dumps(payload).encode()

        calls = {"n": 0}

        def fake_open(_request, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError(
                    "https://api.deepseek.com/chat/completions",
                    503,
                    "Service Unavailable",
                    hdrs=None,
                    fp=io.BytesIO(b"unavailable"),
                )
            return Response()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), patch(
            "legal_daily.llm.urllib.request.urlopen", fake_open
        ):
            result = complete_json("hi", sleeper=lambda _seconds: None)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls["n"], 3)


class ResearchTest(unittest.TestCase):
    def test_journal_list_includes_named_titles(self):
        from legal_daily.research import JOURNALS, journal_queries

        self.assertIn("中国法学", JOURNALS)
        self.assertIn("China Legal Science", JOURNALS)
        self.assertIn("财经法学", JOURNALS)
        self.assertEqual(len(JOURNALS), 30)
        text = " ".join(journal_queries())
        self.assertIn("中国法学", text)
        self.assertIn("Frontiers of Law in China", text)

    def test_select_keeps_known_link_and_longest_journal(self):
        from legal_daily.research import select_research

        allowed = {"https://example.edu/a"}
        items = select_research(
            [
                {
                    "section": "论文",
                    "title": "数据出境的同意规则",
                    "source": "《中国法学》2026年第1期",
                    "one_line": "讨论同意的边界",
                    "link": "https://example.edu/a",
                },
                {
                    "section": "论文",
                    "title": "编造的论文",
                    "source": "中国法学",
                    "one_line": "没有这条页面",
                    "link": "https://example.edu/fake",
                },
                {
                    "section": "论文",
                    "title": "另一篇",
                    "source": "不存在的刊物",
                    "one_line": "期刊不在名单里",
                    "link": "https://example.edu/a",
                },
            ],
            allowed,
            weekly=True,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "中国法学")
        self.assertEqual(items[0]["section"], "论文")

    def test_format_empty_and_fallback(self):
        from legal_daily.research import format_research

        daily = format_research("daily", "2026-10-15", [], [])
        weekly = format_research("weekly", "2026-W42", [], [])
        self.assertIn("今日无新的论文材料。", daily)
        self.assertIn("近 90 天的目录页和公开新闻里没有检索到相关期刊文章。", weekly)
        noted = format_research(
            "weekly",
            "2026-W42",
            [],
            [],
            quiet=[{"label": "《清华法学》2026年第2期", "link": "http://iolaw.cssn.cn/a.shtml", "reason": "empty"}],
            failures=[{"text": "中国法学网没有打开。", "link": "http://iolaw.cssn.cn/fxyjdt/"}],
        )
        self.assertIn("《清华法学》2026年第2期目录里没有网络法题目。", noted)
        self.assertIn("中国法学网没有打开。", noted)
        self.assertNotIn("近 90 天的目录页和公开新闻里没有检索到相关期刊文章。", noted)
        fallback = format_research(
            "daily",
            "2026-10-15",
            [],
            [{"title": "北京互联网法院公开一则数据案例", "link": "https://www.bjinternetcourt.gov.cn/a"}],
        )
        self.assertNotIn("今日无新的论文材料。", fallback)
        self.assertIn("https://www.bjinternetcourt.gov.cn/a", fallback)
        self.assertIn("不能用「展开」", fallback)

    def test_weekly_prompt_survives_json_braces(self):
        from legal_daily.research import _prompt

        text = _prompt("weekly", "")
        self.assertIn('"items"', text)
        self.assertIn("中国法学", text)
        self.assertIn("财经法学", text)

    def test_site_name_is_not_the_journal(self):
        from legal_daily.research import _mentions_journal

        site = {"title": "人工智能时代历史学的研究进路 - 中国社会科学网", "snippet": ""}
        journal = {"title": "《中国社会科学》数据权利研究", "snippet": ""}
        self.assertFalse(_mentions_journal(site))
        self.assertTrue(_mentions_journal(journal))

    def test_weekly_google_query_asks_for_90_days(self):
        from legal_daily.research import WEEKLY_DAYS, _feed_urls

        self.assertEqual(WEEKLY_DAYS, 90)
        bing, google = _feed_urls("中国法学", 5)
        self.assertNotIn("when%3A", bing)
        self.assertNotIn("when%3A", google)
        bing, google = _feed_urls("中国法学", WEEKLY_DAYS)
        self.assertNotIn("when%3A", bing)
        self.assertIn("when%3A90d", google)

    def test_catalog_pages_keep_cyberlaw_titles(self):
        import json
        from datetime import datetime, timedelta
        from urllib.parse import urljoin

        from legal_daily.textutil import CST
        from legal_daily.toc import CLS_HOME, IOLAW_LIST, collect_catalogs

        recent = (datetime.now(CST).date() - timedelta(days=10)).isoformat()
        old = (datetime.now(CST).date() - timedelta(days=120)).isoformat()
        issue = urljoin(IOLAW_LIST, "./a.shtml")
        quiet_issue = urljoin(IOLAW_LIST, "./quiet.shtml")
        cls_issue = urljoin(CLS_HOME, "/portal/list/index.html?id=1934")
        pages = {
            IOLAW_LIST: (
                f'<a href="./a.shtml">《中外法学》2026年第5期要目 {recent}</a>'
                f'<a href="./quiet.shtml">《清华法学》2026年第2期要目 {recent}</a>'
                f'<a href="./old.shtml">《法学研究》2026年第1期要目 {old}</a>'
                f'<a href="./other.shtml">《北方法学》2026年第4期要目 {recent}</a>'
            ),
            issue: "3、人工智能立法的合作规制&nbsp;&nbsp;张三\n1、合同效力的一般理论&nbsp;&nbsp;李四",
            quiet_issue: "2、物权变动的理论&nbsp;&nbsp;赵六",
            CLS_HOME: '<a href="/portal/list/index.html?id=1934">《中国法学》2026年第4期</a>',
            cls_issue: (
                "<li><div><a href=\"/portal/article/index.html?id=1&cid=2\">数字经济时代的广告规制</a></div>"
                "<div><span>王五 , 某大学</span></div></li>"
                "<li><a href=\"/portal/article/index.html?id=2\">物权变动</a><span>赵六</span></li>"
            ),
        }

        def fetcher(url, headers=None):
            if url in pages:
                return pages[url]
            if "api.crossref.org" in url and "China%20Legal%20Science" in url:
                return json.dumps(
                    {
                        "message": {
                            "items": [
                                {
                                    "container-title": ["Legal Science in China and Russia"],
                                    "title": ["Data privacy elsewhere"],
                                    "URL": "https://doi.org/10.fake/1",
                                    "author": [],
                                },
                                {
                                    "container-title": ["China Legal Science"],
                                    "title": ["Platform liability and data"],
                                    "URL": "https://doi.org/10.real/2",
                                    "author": [{"given": "Ann", "family": "Lee"}],
                                },
                            ]
                        }
                    }
                )
            if "api.crossref.org" in url:
                return json.dumps({"message": {"items": []}})
            if "api.openalex.org/sources" in url and "Frontiers" in url:
                return json.dumps(
                    {"results": [{"id": "https://openalex.org/S1", "display_name": "Frontiers of Law in China"}]}
                )
            if "api.openalex.org/sources" in url:
                return json.dumps({"results": []})
            if "api.openalex.org/works" in url:
                return json.dumps(
                    {
                        "results": [
                            {
                                "display_name": "Internet courts and privacy",
                                "authorships": [{"author": {"display_name": "Bo Chen"}}],
                                "doi": "https://doi.org/10.front/1",
                                "primary_location": {
                                    "source": {"display_name": "Frontiers of Law in China"},
                                    "landing_page_url": "https://doi.org/10.front/1",
                                },
                            }
                        ]
                    }
                )
            raise RuntimeError(url)

        result = collect_catalogs(
            fetcher,
            90,
            ["中外法学", "清华法学", "法学研究", "中国法学", "China Legal Science", "Frontiers of Law in China"],
            ["人工智能", "数字经济", "data", "privacy", "platform", "internet"],
            set(),
        )
        titles = [item["title"] for item in result["articles"]]
        self.assertIn("人工智能立法的合作规制", titles)
        self.assertIn("数字经济时代的广告规制", titles)
        self.assertIn("Platform liability and data", titles)
        self.assertIn("Internet courts and privacy", titles)
        self.assertNotIn("合同效力的一般理论", titles)
        self.assertNotIn("物权变动", titles)
        self.assertNotIn("Data privacy elsewhere", titles)
        self.assertEqual(result["articles"][0]["source"], "中外法学")
        self.assertEqual([item["label"] for item in result["quiet"]], ["《清华法学》2026年第2期"])
        self.assertEqual(result["failures"], [])
        from legal_daily.textutil import norm_link

        sent = {norm_link(item["link"]) for item in result["articles"]}
        sent.update(norm_link(item["link"]) for item in result["quiet"])
        again = collect_catalogs(
            fetcher,
            90,
            ["中外法学", "清华法学", "法学研究", "中国法学", "China Legal Science", "Frontiers of Law in China"],
            ["人工智能", "数字经济", "data", "privacy", "platform", "internet"],
            sent,
        )
        self.assertEqual(again["articles"], [])
        self.assertEqual(again["quiet"], [])


class ConfigTest(unittest.TestCase):
    def test_config_strips_journal_marks_and_can_keep_experienced_jobs(self):
        import json
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from legal_daily.careers import classify_opening
        from legal_daily.config import journals

        with TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "journals": ["《中国法学》", "China Legal Science"],
                        "jobs": {"fresh_graduate_only": False},
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"LEGAL_DAILY_CONFIG": str(path)}):
                self.assertEqual(journals(), ("中国法学", "China Legal Science"))
                kept = classify_opening("法务", "", "3年以上工作经验")
        self.assertEqual(kept["experience"], "需经验")


if __name__ == "__main__":
    unittest.main()
