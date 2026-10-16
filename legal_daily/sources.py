from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

from .careers import collect_career_jobs
from .net import fetch_text
from .rss import parse_rss
from .textutil import clip, host_of, is_fresh, norm_link, parse_http_date

NEWS_DAYS = 5
JOB_DAYS = 30

NEWS_QUERIES = [
    "国家互联网信息办公室 人工智能 OR 生成式人工智能 OR 深度合成 OR 算法备案",
    "个人信息保护 OR 数据出境 OR 数据安全 规定 OR 办法",
    "最高人民法院 人工智能 OR 个人信息 OR 数据 典型案例",
    "法律科技 OR 智慧法院 OR 法律人工智能 OR legaltech",
    '"AI Act" OR FTC "artificial intelligence" policy OR guidance',
]

JOB_QUERIES = [
    "数据合规 法务 招聘",
    "数据合规 律师 实习",
    "法律科技 招聘",
    "法律人工智能 招聘",
    "幂律 招聘",
    "华宇元典 招聘",
]

NEWS_TERMS = (
    "人工智能",
    "生成式",
    "深度合成",
    "算法",
    "个人信息",
    "数据",
    "法律",
    "合规",
    "网信",
    "法院",
    "legaltech",
    "隐私",
    "ai act",
    "ftc",
    "ai",
)
JOB_TOPIC = (
    "法律",
    "法务",
    "律师",
    "合规",
    "幂律",
    "华宇",
    "元典",
    "秘塔",
    "智合",
    "法睿",
    "legaltech",
    "隐私",
    "算法",
    "数据",
)
JOB_HIRING = ("招聘", "实习", "校招", "社招", "职位")
JUNK_HOSTS = (
    "zhihu.com",
    "jingyan.baidu.com",
    "zhidao.baidu.com",
    "baike.baidu.com",
    "tieba.baidu.com",
    "wenku.baidu.com",
    "douyin.com",
    "bilibili.com",
    "xiaohongshu.com",
    "wikipedia.org",
)


def _rss_urls(query):
    encoded = quote_plus(query)
    return [
        f"https://www.bing.com/news/search?q={encoded}&format=rss&setlang=zh-Hans",
        "https://news.google.com/rss/search?q="
        + encoded
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    ]


def _blob(item):
    return f"{item.get('title') or ''} {item.get('snippet') or ''}".lower()


def _junk_host(link):
    host = host_of(link)
    return any(host == name or host.endswith("." + name) for name in JUNK_HOSTS)


def accept_item(kind, item):
    if _junk_host(item.get("link") or ""):
        return False
    text = _blob(item)
    if kind == "job":
        title = (item.get("title") or "").lower()
        return any(term in title for term in JOB_HIRING) and any(term in text for term in JOB_TOPIC)
    return any(term in text for term in NEWS_TERMS)


def _link_score(link):
    host = host_of(link)
    if host.endswith(".gov.cn") or "court.gov.cn" in host:
        return 3
    if "news.google." in host:
        return 0
    return 1


def _keep_better(current, incoming):
    if _link_score(incoming["link"]) > _link_score(current["link"]):
        return incoming
    return current


def collect(kind, queries, days, fetcher=fetch_text):
    tasks = []
    for query in queries:
        for url in _rss_urls(query):
            tasks.append((query, url))

    found = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetcher, url): (query, url) for query, url in tasks}
        for future in as_completed(futures):
            query, url = futures[future]
            try:
                xml = future.result()
            except Exception as exc:
                print(f"source skip {url}: {exc}")
                continue
            if not xml:
                continue
            for item in parse_rss(xml):
                moment = parse_http_date(item["date"])
                if not is_fresh(moment, days):
                    continue
                candidate = {
                    "kind": kind,
                    "query": query,
                    "title": item["title"],
                    "link": item["link"],
                    "date": item["date"],
                    "snippet": item["snippet"],
                }
                if not accept_item(kind, candidate):
                    print(f"丢弃无关 {kind} {candidate['title']}")
                    continue
                if kind == "job":
                    candidate["experience"] = "未写明"
                    candidate["snippet"] = clip("年限未写明 " + (candidate.get("snippet") or ""), 240)
                found.append(candidate)

    deduped = {}
    order = []
    for item in found:
        key = clip(item["title"], 40).lower()
        if key not in deduped:
            deduped[key] = item
            order.append(key)
            continue
        deduped[key] = _keep_better(deduped[key], item)
    items = [deduped[key] for key in order]
    return items[:36 if kind == "news" else 24]


def _merge_jobs(career_jobs, rss_jobs):
    chosen = []
    seen = set()
    for item in list(career_jobs or []) + list(rss_jobs or []):
        key = norm_link(item.get("link")) or item.get("title")
        if key in seen:
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) >= 48:
            break
    return chosen


def collect_all(fetcher=fetch_text):
    news = collect("news", NEWS_QUERIES, NEWS_DAYS, fetcher=fetcher)
    rss_jobs = collect("job", JOB_QUERIES, JOB_DAYS, fetcher=fetcher)
    career_jobs = collect_career_jobs(fetcher)
    return news, _merge_jobs(career_jobs, rss_jobs)


def material_block(items):
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            "\n".join(
                [
                    f"[{index}] kind={item['kind']} date={item.get('date') or '未知'}",
                    f"title: {item['title']}",
                    f"link: {item['link']}",
                    "tag: "
                    + "·".join(part for part in (item.get("employment"), item.get("experience")) if part),
                    f"snippet: {item.get('snippet') or '无'}",
                ]
            )
        )
    return "\n\n".join(lines)


def allowed_links(items):
    return {item["link"] for item in items} | {norm_link(item["link"]) for item in items}
