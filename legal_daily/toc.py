import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import quote, urljoin

from .textutil import CST, is_fresh, norm_link, one_line

IOLAW_LIST = "http://iolaw.cssn.cn/fxyjdt/"
CLS_HOME = "https://clsjp.chinalaw.org.cn/"
API_HEADERS = {"User-Agent": "LegalDaily/1.0 (mailto:legal-daily@users.noreply.github.com)"}
SKIP_AUTHORS = {"摘要", "关键词", "目录", "专题", "内容", "编者"}


def collect_catalogs(fetcher, days, journals, terms, seen):
    articles = []
    quiet = []
    failures = []
    allowed = set(journals)
    _collect_iolaw(fetcher, days, allowed, terms, seen, articles, quiet, failures)
    _collect_cls(fetcher, allowed, terms, seen, articles, quiet, failures)
    english = [name for name in journals if str(name).isascii()]
    _collect_crossref(fetcher, days, terms, seen, articles, failures, english)
    _collect_openalex(fetcher, days, terms, seen, articles, failures, english)
    deduped = []
    seen_titles = set()
    for item in articles:
        key = one_line(item["title"]).lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append(item)
    print(f"期刊目录 {len(deduped)} 篇，无网络法题目 {len(quiet)} 期，打不开 {len(failures)} 处")
    return {"articles": deduped[:24], "quiet": quiet[:8], "failures": failures}


def _collect_iolaw(fetcher, days, journals, terms, seen, articles, quiet, failures):
    try:
        html = fetcher(IOLAW_LIST)
    except Exception as exc:
        print(f"目录跳过 中国法学网 {exc}")
        failures.append({"text": "中国法学网没有打开。", "link": IOLAW_LIST})
        return
    issues = []
    for href, journal, year, issue, date in _iolaw_issues(html):
        if journal not in journals or not _date_within(date, days):
            continue
        link = urljoin(IOLAW_LIST, href)
        if norm_link(link) in seen:
            continue
        issues.append((link, journal, f"《{journal}》{year}年第{issue}期"))
    _fetch_issues(fetcher, issues[:12], terms, seen, articles, quiet, failures, _iolaw_articles)


def _collect_cls(fetcher, journals, terms, seen, articles, quiet, failures):
    try:
        html = fetcher(CLS_HOME)
    except Exception as exc:
        print(f"目录跳过 中国法学杂志社 {exc}")
        failures.append({"text": "中国法学杂志社没有打开。", "link": CLS_HOME})
        return
    issues = []
    for href, journal, year, issue in _cls_issues(html):
        if journal not in journals:
            continue
        link = urljoin(CLS_HOME, href)
        if norm_link(link) in seen:
            continue
        issues.append((link, journal, f"《{journal}》{year}年第{issue}期"))
    _fetch_issues(fetcher, issues[:6], terms, seen, articles, quiet, failures, _cls_articles)


def _fetch_issues(fetcher, issues, terms, seen, articles, quiet, failures, parser):
    if not issues:
        return

    def load(issue):
        link, journal, label = issue
        try:
            return issue, fetcher(link), None
        except Exception as exc:
            return issue, "", exc

    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(load, issues))
    for (link, journal, label), html, exc in fetched:
        if exc is not None:
            print(f"目录跳过 {label} {exc}")
            failures.append({"text": f"{label}的目录页没有打开。", "link": link})
            continue
        rows = parser(html, link)
        already = any(norm_link(row["link"]) in seen for row in rows)
        matched = [
            _article(journal, row["title"], row["author"], row["link"])
            for row in rows
            if _topic(row["title"], terms) and norm_link(row["link"]) not in seen
        ]
        if matched:
            articles.extend(matched)
        elif rows and not already:
            quiet.append({"label": label, "link": link, "reason": "empty"})
        elif not rows:
            quiet.append({"label": label, "link": link, "reason": "unparsed"})


def _collect_crossref(fetcher, days, terms, seen, articles, failures, english):
    since = _since(days)
    for journal in english:
        url = (
            "https://api.crossref.org/works?filter="
            f"container-title:{quote(journal)},from-pub-date:{since},type:journal-article"
            "&rows=20&select=title,author,container-title,URL"
        )
        try:
            payload = json.loads(fetcher(url, headers=API_HEADERS))
        except Exception as exc:
            print(f"目录跳过 Crossref {journal} {exc}")
            failures.append({"text": f"Crossref 没有打开《{journal}》。", "link": "https://api.crossref.org"})
            continue
        for item in payload.get("message", {}).get("items") or []:
            names = item.get("container-title") or []
            if not any(one_line(name).lower() == journal.lower() for name in names):
                continue
            title = one_line((item.get("title") or [""])[0])
            link = one_line(item.get("URL"))
            if not title or not link.startswith("http") or not _topic(title, terms):
                continue
            if norm_link(link) in seen:
                continue
            authors = []
            for person in item.get("author") or []:
                name = one_line(f"{person.get('given') or ''} {person.get('family') or ''}")
                if name:
                    authors.append(name)
            articles.append(_article(journal, title, "、".join(authors[:3]), link))


def _collect_openalex(fetcher, days, terms, seen, articles, failures, english):
    since = _since(days)
    for journal in english:
        source_url = (
            "https://api.openalex.org/sources?filter="
            f"display_name.search:{quote(journal)}&per-page=5&mailto=legal-daily@users.noreply.github.com"
        )
        try:
            sources = json.loads(fetcher(source_url, headers=API_HEADERS))
        except Exception as exc:
            print(f"目录跳过 OpenAlex {journal} {exc}")
            failures.append({"text": f"OpenAlex 没有打开《{journal}》。", "link": "https://api.openalex.org"})
            continue
        source_id = ""
        for source in sources.get("results") or []:
            if one_line(source.get("display_name")).lower() == journal.lower():
                source_id = one_line(source.get("id")).rsplit("/", 1)[-1]
                break
        if not source_id:
            continue
        works_url = (
            "https://api.openalex.org/works?filter="
            f"primary_location.source.id:{source_id},from_publication_date:{since}"
            "&per-page=20&select=display_name,authorships,doi,primary_location"
            "&mailto=legal-daily@users.noreply.github.com"
        )
        try:
            works = json.loads(fetcher(works_url, headers=API_HEADERS))
        except Exception as exc:
            print(f"目录跳过 OpenAlex 文章 {journal} {exc}")
            failures.append({"text": f"OpenAlex 没有打开《{journal}》的文章列表。", "link": "https://api.openalex.org"})
            continue
        for item in works.get("results") or []:
            source = ((item.get("primary_location") or {}).get("source") or {})
            if one_line(source.get("display_name")).lower() != journal.lower():
                continue
            title = one_line(item.get("display_name"))
            location = item.get("primary_location") or {}
            link = one_line(location.get("landing_page_url") or item.get("doi"))
            if link.startswith("doi:"):
                link = "https://doi.org/" + link[4:]
            if not title or not link.startswith("http") or not _topic(title, terms):
                continue
            if norm_link(link) in seen:
                continue
            authors = []
            for person in item.get("authorships") or []:
                name = one_line((person.get("author") or {}).get("display_name"))
                if name:
                    authors.append(name)
            articles.append(_article(journal, title, "、".join(authors[:3]), link))


def _iolaw_issues(html):
    found = []
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html or "", flags=re.I | re.S):
        text = _anchor_text(match.group(2))
        parsed = re.search(r"《([^》]+)》(20\d{2})年第(\d+)期要目\s+(20\d{2}-\d{2}-\d{2})", text)
        if not parsed:
            continue
        found.append((match.group(1), parsed.group(1), parsed.group(2), parsed.group(3), parsed.group(4)))
    return found


def _iolaw_articles(html, page_link):
    rows = []
    for raw in _text_lines(html):
        numbered = re.match(r"^(\d+)[、.]\s*(.+?)\s{2,}(\S(?:.*\S)?)$", raw)
        if numbered:
            title = _clean_title(numbered.group(2))
            author = one_line(numbered.group(3))
        else:
            signed = re.match(r"^([\u4e00-\u9fff]{2,4})：(\S.{7,80})$", raw)
            if not signed or signed.group(1) in SKIP_AUTHORS:
                continue
            author = signed.group(1)
            title = _clean_title(signed.group(2))
        if len(title) < 6 or not author:
            continue
        rows.append({"title": title, "author": author, "link": page_link})
    return rows


def _cls_issues(html):
    found = []
    seen = set()
    for match in re.finditer(
        r'href="([^"]*?/portal/list/index\.html\?id=\d+)"[^>]*>\s*《([^》]+)》\s*(20\d{2})年第(\d+)期',
        html or "",
        flags=re.I,
    ):
        href = match.group(1)
        if href in seen:
            continue
        seen.add(href)
        found.append((href, one_line(match.group(2)), match.group(3), match.group(4)))
    return found


def _cls_articles(html, page_link):
    rows = []
    seen = set()
    for block in re.split(r"<li\b", html or "", flags=re.I)[1:]:
        match = re.search(
            r'href="([^"]*?/portal/article/[^"]+)"[^>]*>\s*([^<]{4,80})</a>.*?<span>\s*([^<]{1,80})\s*</span>',
            block,
            flags=re.I | re.S,
        )
        if not match:
            continue
        title = _clean_title(match.group(2))
        link = urljoin(page_link, match.group(1))
        if len(title) < 6 or norm_link(link) in seen or link.lower().endswith(".pdf"):
            continue
        seen.add(norm_link(link))
        author = re.split(r"[,，]", unescape(match.group(3)))[0].strip()
        rows.append({"title": title, "author": one_line(author), "link": link})
    return rows


def _article(journal, title, author, link):
    return {
        "section": "论文",
        "title": one_line(title),
        "source": journal,
        "one_line": one_line(author) or "公开目录没有写出作者",
        "link": link,
    }


def _topic(title, terms):
    lowered = title.lower()
    return any(term.lower() in lowered for term in terms)


def _date_within(value, days):
    try:
        moment = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=CST)
    except ValueError:
        return False
    return is_fresh(moment, days)


def _since(days):
    return (datetime.now(CST).date() - timedelta(days=days)).isoformat()


def _anchor_text(value):
    text = re.sub(r"(?is)<[^>]+>", " ", value or "")
    return one_line(unescape(text))


def _text_lines(html):
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", "\n", cleaned)
    lines = []
    for raw in unescape(cleaned).splitlines():
        line = raw.replace("\xa0", " ").strip()
        if line:
            lines.append(line)
    return lines


def _clean_title(value):
    title = unescape(value).replace("\xa0", " ")
    title = re.sub(r"[（(]\d+[）)]\s*$", "", title)
    return one_line(title)
