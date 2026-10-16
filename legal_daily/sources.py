from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

from .careers import FETCHERS, collect_career_jobs
from .config import enabled_companies, job_queries, job_topic_terms, news_queries, news_terms
from .net import fetch_text
from .rss import parse_rss
from .textutil import clip, host_of, is_fresh, norm_link, parse_http_date

NEWS_DAYS = 5
JOB_DAYS = 30

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
        return any(term.lower() in title for term in JOB_HIRING) and any(term.lower() in text for term in job_topic_terms())
    return any(term.lower() in text for term in news_terms())


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


def public_job_queries():
    known = {name for name, _func in FETCHERS}
    queries = list(job_queries())
    for name in enabled_companies():
        if name in known:
            continue
        query = f"{name} 招聘"
        if query not in queries:
            queries.append(query)
    return tuple(queries)


def collect_all(fetcher=fetch_text):
    news = collect("news", news_queries(), NEWS_DAYS, fetcher=fetcher)
    rss_jobs = collect("job", public_job_queries(), JOB_DAYS, fetcher=fetcher)
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
