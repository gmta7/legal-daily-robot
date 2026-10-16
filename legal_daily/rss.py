import re
from html import unescape

from .textutil import clip, one_line


def _tag(block, name):
    cdata = re.search(
        rf"<{name}\b[^>]*>\s*<!\[CDATA\[(.*?)\]\]>\s*</{name}>",
        block,
        flags=re.I | re.S,
    )
    if cdata:
        return one_line(unescape(cdata.group(1)))
    plain = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, flags=re.I | re.S)
    if not plain:
        return ""
    text = re.sub(r"(?is)<[^>]+>", " ", plain.group(1))
    return one_line(unescape(text))


def parse_rss(xml, limit=8):
    items = []
    for block in re.split(r"<item\b", xml or "", flags=re.I)[1:]:
        title = _tag(block, "title")
        link = _tag(block, "link") or _tag(block, "guid")
        if not title or not link.startswith("http"):
            continue
        items.append(
            {
                "title": clip(title, 180),
                "link": link.strip(),
                "date": _tag(block, "pubDate"),
                "snippet": clip(_tag(block, "description"), 240),
            }
        )
        if len(items) >= limit:
            break
    return items
