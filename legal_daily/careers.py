import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode

from .config import enabled_companies, fresh_graduate_only
from .textutil import clip, one_line

KEYWORDS = ("法务", "合规", "隐私")
TITLE_TERMS = ("法务", "律师", "隐私", "合规", "法律", "知识产权")
PAGE_SIZE = 20
PER_COMPANY = 8
TOTAL_CAP = 48
_CN_DIGIT = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_YEAR = r"([0-9]{1,2}|[一二三四五六七八九十两]{1,3})"


def _parse(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read(fetcher, url, data, headers):
    try:
        return fetcher(url, timeout=15, data=data, headers=headers)
    except Exception as exc:
        print(f"官网跳过 {url[:90]} {exc}")
        return ""


def _post_json(fetcher, url, body, headers):
    merged = {"Content-Type": "application/json", "Accept": "application/json"}
    merged.update(headers)
    raw = _read(fetcher, url, json.dumps(body, ensure_ascii=False).encode(), merged)
    return _parse(raw)


def _post_form(fetcher, url, body, headers):
    merged = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    merged.update(headers)
    raw = _read(fetcher, url, urlencode(body).encode(), merged)
    return _parse(raw)


def _relevant(title):
    text = one_line(title)
    return any(term in text for term in TITLE_TERMS)


def _cn_number(token):
    token = one_line(token)
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if len(token) == 2 and token[0] == "十" and token[1] in _CN_DIGIT:
        return 10 + _CN_DIGIT[token[1]]
    if len(token) == 1 and token in _CN_DIGIT:
        return _CN_DIGIT[token]
    return None


def _year_requirement(text, match):
    span = text[max(0, match.start() - 4) : match.end() + 8]
    if len(one_line(text)) <= 16 or any(word in span for word in ("经验", "工作", "年限")):
        return _cn_number(match.group(1))
    return None


def _minimum_years(text):
    ranged = re.search(rf"(?<![0-9]){_YEAR}\s*[-~～至到]\s*{_YEAR}\s*年", text)
    if ranged:
        low = _year_requirement(text, ranged)
        if low is not None:
            return low
    above = re.search(rf"(?<![0-9]){_YEAR}\s*年\s*(?:及以上|以上|或以上)", text)
    if above:
        value = _year_requirement(text, above)
        if value is not None:
            return value
    at_least = re.search(rf"至少\s*{_YEAR}\s*年", text)
    if at_least:
        return _cn_number(at_least.group(1))
    named = re.search(rf"(?<![0-9]){_YEAR}\s*年(?:及以上|以上)?(?:相关)?(?:工作)?经验", text)
    if named:
        return _cn_number(named.group(1))
    return None


def _clauses(text):
    clauses = []
    for sentence in re.split(r"[。；;\n]+", text or ""):
        if "优先" not in sentence:
            if sentence.strip():
                clauses.append(sentence)
            continue
        for piece in re.split(r"[，,]", sentence):
            if piece.strip() and "优先" not in piece:
                clauses.append(piece)
    return clauses


def _requires_experience(text):
    for clause in _clauses(text):
        years = _minimum_years(clause)
        if years is not None and years >= 1:
            return True
        if any(phrase in clause for phrase in ("具备工作经验", "有相关工作经验", "有工作经验", "需要工作经验", "须有工作经验")):
            return True
    return False


def _accepts_fresh_graduate(text):
    for clause in _clauses(text):
        years = _minimum_years(clause)
        if years == 0:
            return True
    return False


def classify_opening(title, channel="", detail=""):
    """应届生没有全职经验。返回 None 表示丢掉。"""
    title = one_line(title)
    channel = one_line(channel)
    detail = one_line(detail)
    requires = _requires_experience("\n".join((title, channel, detail)))
    if requires and fresh_graduate_only():
        return None
    if "实习" in title or "实习" in channel:
        return {"employment": "实习", "experience": "应届"}
    blob = title + channel
    if any(word in blob for word in ("应届", "校招", "在校")) or _accepts_fresh_graduate(detail):
        return {"employment": "正式", "experience": "应届"}
    if any(phrase in (title + channel + detail) for phrase in ("经验不限", "不限经验", "不限年限", "年限不限", "无需经验")):
        return {"employment": "正式", "experience": "经验不限"}
    if requires:
        return {"employment": "正式", "experience": "需经验"}
    return {"employment": "正式", "experience": "未写明"}


def _item(company, title, link, city="", detail="", channel=""):
    title = one_line(title)
    link = one_line(link)
    if not _relevant(title) or not link.startswith("http"):
        return None
    opening = classify_opening(title, channel, detail)
    if opening is None:
        print(f"丢弃需经验 {company} {title}")
        return None
    snippet = clip(
        " ".join(
            part
            for part in (opening["employment"], opening["experience"], one_line(city), one_line(detail))
            if part
        ),
        180,
    )
    return {
        "kind": "job",
        "query": f"官网 {company}",
        "title": f"{company}｜{title}",
        "link": link,
        "date": "",
        "snippet": snippet,
        "employment": opening["employment"],
        "experience": opening["experience"],
    }


def _finish(found):
    chosen = []
    seen = set()
    for item in found:
        if item["link"] in seen:
            continue
        seen.add(item["link"])
        chosen.append(item)
        if len(chosen) >= PER_COMPANY:
            break
    return chosen


def _place(value):
    if isinstance(value, dict):
        return one_line(value.get("name") or value.get("i18n_name"))
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                names.append(one_line(item.get("name")))
            else:
                names.append(one_line(item))
        return " ".join(name for name in names if name)
    return one_line(value)


def _detail(*parts):
    return " ".join(one_line(part) for part in parts if one_line(part))


def _feishu(fetcher, company, url, origin, link_of, extra_body, channel=""):
    found = []
    headers = {"Origin": origin, "Referer": origin + "/"}
    for keyword in KEYWORDS:
        body = {
            "keyword": keyword,
            "limit": PAGE_SIZE,
            "offset": 0,
            "portal_type": 3,
            "portal_entrance": 1,
            "language": "zh",
        }
        body.update(extra_body)
        payload = _post_json(fetcher, url, body, headers)
        rows = ((payload.get("data") or {}).get("job_post_list")) or []
        for row in rows:
            job_id = one_line(row.get("id"))
            item = _item(
                company,
                row.get("title"),
                link_of(job_id) if job_id else "",
                _place(row.get("city_info")),
                _detail(row.get("requirement"), row.get("description")),
                channel,
            )
            if item:
                found.append(item)
    return _finish(found)


def _bytedance(fetcher):
    found = []
    for recruitment_id, channel, link_of in (
        (
            "101",
            "社招",
            lambda job_id: f"https://jobs.bytedance.com/experienced/position/{job_id}/detail",
        ),
        (
            "201",
            "校招",
            lambda job_id: f"https://jobs.bytedance.com/campus/position/{job_id}/detail",
        ),
    ):
        found.extend(
            _feishu(
                fetcher,
                "字节跳动",
                "https://jobs.bytedance.com/api/v1/search/job/posts",
                "https://jobs.bytedance.com",
                link_of,
                {"recruitment_id_list": [recruitment_id]},
                channel,
            )
        )
    return _finish(found)


def _xiaomi(fetcher):
    return _feishu(
        fetcher,
        "小米",
        "https://xiaomi.jobs.f.mioffice.cn/api/v1/search/job/posts",
        "https://xiaomi.jobs.f.mioffice.cn",
        lambda job_id: f"https://xiaomi.jobs.f.mioffice.cn/campus/position/{job_id}/detail",
        {},
    )


def _tencent(fetcher):
    found = []
    for keyword in KEYWORDS:
        payload = _post_json(
            fetcher,
            "https://join.qq.com/api/v1/position/searchPosition",
            {"keyword": keyword, "pageIndex": 1, "pageSize": PAGE_SIZE},
            {"Origin": "https://join.qq.com", "Referer": "https://join.qq.com/post.html"},
        )
        rows = ((payload.get("data") or {}).get("positionList")) or []
        for row in rows:
            post_id = one_line(row.get("postId"))
            link = f"https://join.qq.com/post_detail.html?postid={post_id}" if post_id else ""
            item = _item(
                "腾讯",
                row.get("positionTitle"),
                link,
                row.get("workCities"),
                "",
                row.get("recruitLabelName"),
            )
            if item:
                found.append(item)
    return _finish(found)


def _netease(fetcher):
    found = []
    for keyword in KEYWORDS:
        payload = _post_json(
            fetcher,
            "https://hr.163.com/api/hr163/position/queryPage",
            {"currentPage": 1, "pageSize": PAGE_SIZE, "keyword": keyword},
            {"Referer": "https://hr.163.com/"},
        )
        rows = ((payload.get("data") or {}).get("list")) or []
        for row in rows:
            job_id = one_line(row.get("id"))
            link = f"https://hr.163.com/job-detail.html?id={job_id}" if job_id else ""
            item = _item(
                "网易",
                row.get("name"),
                link,
                _place(row.get("workPlaceNameList")),
                _detail(row.get("reqWorkYearsName"), row.get("requirement"), row.get("description")),
            )
            if item:
                found.append(item)
    return _finish(found)


def _oppo(fetcher):
    found = []
    for keyword in KEYWORDS:
        payload = _post_json(
            fetcher,
            "https://careers.oppo.com/openapi/position/pageNew",
            {"pageNum": 1, "pageSize": PAGE_SIZE, "positionName": keyword},
            {"Origin": "https://careers.oppo.com", "Referer": "https://careers.oppo.com/"},
        )
        rows = ((payload.get("data") or {}).get("records")) or []
        for row in rows:
            job_id = one_line(row.get("idRecruitPosition"))
            link = f"https://careers.oppo.com/#/campus/talent/positionDetail/{job_id}" if job_id else ""
            item = _item(
                "OPPO",
                row.get("positionName"),
                link,
                "",
                row.get("positionDesc"),
                row.get("recruitmentTypeName"),
            )
            if item:
                found.append(item)
    return _finish(found)


def _baidu(fetcher):
    found = []
    channels = (("SOCIAL", "社招"), ("GRADUATE", "校招"), ("INTERN", "实习"))
    for keyword in KEYWORDS:
        for recruit_type, channel in channels:
            payload = _post_form(
                fetcher,
                "https://talent.baidu.com/httservice/getPostListNew",
                {"recruitType": recruit_type, "keyWord": keyword, "curPage": 1, "pageSize": PAGE_SIZE},
                {
                    "Origin": "https://talent.baidu.com",
                    "Referer": f"https://talent.baidu.com/jobs/list?recruitType={recruit_type}",
                },
            )
            rows = ((payload.get("data") or {}).get("list")) or []
            for row in rows:
                post_id = one_line(row.get("postId"))
                link = (
                    f"https://talent.baidu.com/jobs/detail/{recruit_type}/{post_id}" if post_id else ""
                )
                item = _item(
                    "百度",
                    row.get("name"),
                    link,
                    row.get("orgName"),
                    row.get("serviceCondition"),
                    channel,
                )
                if item:
                    found.append(item)
    return _finish(found)


def _meituan(fetcher):
    found = []
    for keyword in KEYWORDS:
        payload = _post_json(
            fetcher,
            "https://zhaopin.meituan.com/api/official/job/getJobList",
            {"page": {"pageNo": 1, "pageSize": PAGE_SIZE}, "keywords": keyword},
            {"Origin": "https://zhaopin.meituan.com", "Referer": "https://zhaopin.meituan.com/web/social"},
        )
        rows = ((payload.get("data") or {}).get("list")) or []
        for row in rows:
            job_id = one_line(row.get("jobUnionId"))
            link = (
                f"https://zhaopin.meituan.com/web/position/detail?jobUnionId={job_id}&jobShareType=1"
                if job_id
                else ""
            )
            item = _item(
                "美团",
                row.get("name"),
                link,
                _place(row.get("cityList")),
                _detail(row.get("workYear"), row.get("jobRequirement"), row.get("jobDuty")),
            )
            if item:
                found.append(item)
    return _finish(found)


def _didi(fetcher):
    found = []
    for keyword in KEYWORDS:
        query = urlencode({"page": 1, "size": PAGE_SIZE, "jobName": keyword})
        raw = _read(
            fetcher,
            f"https://talent.didiglobal.com/recruit-portal-service/api/job/front/list?{query}",
            None,
            {"Referer": "https://talent.didiglobal.com/", "Accept": "application/json"},
        )
        rows = ((_parse(raw).get("data") or {}).get("items")) or []
        for row in rows:
            job_id = one_line(row.get("jdId"))
            link = f"https://talent.didiglobal.com/campus#/position/{job_id}/detail" if job_id else ""
            item = _item(
                "滴滴",
                row.get("jobName"),
                link,
                row.get("workArea"),
                _detail(row.get("jobQualification"), row.get("jobDuty")),
            )
            if item:
                found.append(item)
    return _finish(found)


def _ant(fetcher):
    found = []
    for keyword in KEYWORDS:
        payload = _post_json(
            fetcher,
            "https://hrcareersweb.antgroup.com/api/social/position/search",
            {
                "key": keyword,
                "pageIndex": 1,
                "pageSize": PAGE_SIZE,
                "language": "zh",
                "channel": "group_official_site",
                "regions": "",
                "categories": "",
                "subCategories": "",
                "bgCode": "",
                "socialQrCode": "",
            },
            {
                "Origin": "https://talent.antgroup.com",
                "Referer": "https://talent.antgroup.com/off-campus-position",
            },
        )
        rows = payload.get("content") or []
        for row in rows:
            job_id = one_line(row.get("id"))
            link = f"https://talent.antgroup.com/off-campus-position?positionId={job_id}" if job_id else ""
            item = _item(
                "蚂蚁集团",
                row.get("name"),
                link,
                _place(row.get("workLocations")),
                "",
                _place(row.get("categories")),
            )
            if item:
                found.append(item)
    return _finish(found)


FETCHERS = (
    ("腾讯", _tencent),
    ("字节跳动", _bytedance),
    ("小米", _xiaomi),
    ("网易", _netease),
    ("OPPO", _oppo),
    ("百度", _baidu),
    ("美团", _meituan),
    ("滴滴", _didi),
    ("蚂蚁集团", _ant),
)


def collect_career_jobs(fetcher):
    found = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        chosen_fetchers = [(name, func) for name, func in FETCHERS if name in set(enabled_companies())]
        futures = {pool.submit(func, fetcher): name for name, func in chosen_fetchers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                rows = future.result()
            except Exception as exc:
                print(f"官网跳过 {name} {exc}")
                continue
            print(f"官网 {name} {len(rows)} 条")
            found.extend(rows)
    chosen = []
    seen = set()
    for item in found:
        if item["link"] in seen:
            continue
        seen.add(item["link"])
        chosen.append(item)
        if len(chosen) >= TOTAL_CAP:
            break
    return chosen
