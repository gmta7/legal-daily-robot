import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CST = timezone(timedelta(hours=8))


def today_shanghai():
    return datetime.now(CST).strftime("%Y-%m-%d")


def one_line(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clip(value, limit):
    text = one_line(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def parse_http_date(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_fresh(moment, days):
    if moment is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return moment >= cutoff


def html_to_text(html, limit=6000):
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def norm_link(url):
    parts = urlsplit((url or "").strip())
    if not parts.scheme or not parts.netloc:
        return (url or "").strip()
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def host_of(url):
    return urlsplit(url or "").netloc.lower()
