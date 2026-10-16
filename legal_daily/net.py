import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (compatible; LegalDaily/1.0; +https://github.com/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def fetch_text(url, timeout=20, data=None, headers=None):
    req_headers = {"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/html, */*"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} {url} {detail}") from exc
    return raw.decode(charset, "replace")
