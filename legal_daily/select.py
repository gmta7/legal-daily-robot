from .config import job_limit
from .textutil import norm_link, one_line

NEWS_CATEGORIES = {"新规", "案件", "评论", "国外"}
TRACKS = {"合规", "Legaltech"}
TIERS = ["复合", "技术", "合规", "创新"]
EMPLOYMENT = {"实习", "正式"}
EXPERIENCE = {"应届", "经验不限", "未写明", "需经验"}


def _as_bool(value):
    return value is True or str(value).lower() == "true"


def _points(value, limit=3):
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = one_line(item)
        if text:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _link_ok(link, allowed):
    text = (link or "").strip()
    return bool(text) and (text in allowed or norm_link(text) in allowed)


def _resolve_link(raw, allowed, sources, title_keys):
    link = (raw.get("link") or "").strip()
    if _link_ok(link, allowed):
        return link
    titles = [one_line(raw.get(key)).lower() for key in title_keys]
    titles = [title for title in titles if len(title) >= 8]
    for source in sources or []:
        source_title = one_line(source.get("title")).lower()
        if len(source_title) < 8:
            continue
        for title in titles:
            if title == source_title or title[:24] == source_title[:24]:
                return (source.get("link") or "").strip()
    return ""


def select_news(raw_items, allowed, sources=None):
    selected = []
    for raw in raw_items or []:
        if not isinstance(raw, dict):
            continue
        link = _resolve_link(raw, allowed, sources, ("title_zh", "title_en"))
        title = one_line(raw.get("title_zh"))
        summary = one_line(raw.get("one_line_zh"))
        if not title or not summary or not _link_ok(link, allowed):
            continue
        category = raw.get("category")
        if category not in NEWS_CATEGORIES:
            category = "评论"
        track = raw.get("track")
        if track not in TRACKS:
            track = "合规"
        selected.append(
            {
                "category": category,
                "track": track,
                "important": _as_bool(raw.get("important")),
                "title_zh": title,
                "title_en": one_line(raw.get("title_en")) or title,
                "one_line_zh": summary,
                "one_line_en": one_line(raw.get("one_line_en")) or "See the Chinese summary.",
                "points": _points(raw.get("points")),
                "for_you": one_line(raw.get("for_you")) or "可以当作面试里的一条近期动态来讲。",
                "link": link,
            }
        )
        if len(selected) >= 8:
            break
    for index, item in enumerate(selected, start=1):
        item["n"] = index
    return selected


def _matched_source(link, sources):
    wanted = norm_link(link)
    for source in sources or []:
        if source.get("link") == link or norm_link(source.get("link")) == wanted:
            return source
    return None


def select_jobs(raw_items, allowed, seen_links, sources=None):
    seen = {norm_link(link) for link in seen_links or []}
    grouped = {tier: [] for tier in TIERS}
    for raw in raw_items or []:
        if not isinstance(raw, dict):
            continue
        link = _resolve_link(raw, allowed, sources, ("role", "org"))
        if not link or norm_link(link) in seen:
            continue
        org = one_line(raw.get("org"))
        role = one_line(raw.get("role"))
        practice = one_line(raw.get("practice"))
        if not org or not role or not practice:
            continue
        tier = raw.get("tier")
        if tier not in grouped:
            tier = "合规"
        source = _matched_source(link, sources)
        employment = (source or {}).get("employment") or raw.get("employment")
        if employment not in EMPLOYMENT:
            employment = "正式"
        experience = (source or {}).get("experience") or raw.get("experience")
        if experience not in EXPERIENCE:
            experience = "未写明"
        grouped[tier].append(
            {
                "tier": tier,
                "employment": employment,
                "experience": experience,
                "org": org,
                "role": role,
                "city": one_line(raw.get("city")),
                "deadline": one_line(raw.get("deadline")),
                "practice": practice,
                "requirements": _points(raw.get("requirements")),
                "one_line_en": one_line(raw.get("one_line_en")) or practice,
                "alert": _as_bool(raw.get("alert")),
                "link": link,
            }
        )
    ordered = []
    for tier in TIERS:
        ordered.extend(grouped[tier])
        if len(ordered) >= job_limit():
            break
    ordered = ordered[: job_limit()]
    for index, item in enumerate(ordered, start=1):
        item["n"] = index
    return ordered
