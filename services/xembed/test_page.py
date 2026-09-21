"""Landing rewriter checks. PAGE_REGEX must stay identical to the JS literal."""

import re
from pathlib import Path
from urllib.parse import urlsplit


PAGE = Path(__file__).with_name("static") / "index.html"
HOSTS = {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com", "x.milkhaus.net"}
MIRROR = "x.milkhaus.net"


def extracted_pattern():
    html = PAGE.read_text()
    match = re.search(r"const pathPattern = /(.*)/;", html)
    assert match, "generated page has no path regex"
    return match.group(1).replace(r"\/", "/")


def rewrite(raw):
    raw = raw.strip()
    if not raw or re.search(r"\s|[\x00-\x1f\x7f]|\\", raw) or raw.startswith("//"):
        return None
    if not re.match(r"https?://", raw, re.I):
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", raw):
            return None
        if re.split(r"[/?#]", raw, 1)[0].lower() not in HOSTS:
            return None
        raw = "https://" + raw
    authority = re.split(r"[/?#]", re.sub(r"^https?://", "", raw, flags=re.I), 1)[0]
    if "@" in authority or re.search(r":\d+$", authority):
        return None
    raw_path = re.split(r"[?#]", re.sub(r"^https?://[^/?#]*", "", raw, flags=re.I), 1)[0] or "/"
    if "%" in raw_path or any(part in (".", "..") for part in raw_path.split("/")):
        return None
    url = urlsplit(raw)
    if url.scheme.lower() not in ("http", "https") or url.username or url.password or url.port or (url.hostname or "").lower() not in HOSTS:
        return None
    if not re.fullmatch(extracted_pattern(), url.path):
        return None
    return f"https://{MIRROR}{url.path}"


def run_checks():
    assert extracted_pattern() == r"^/(?:[A-Za-z0-9_]{1,15}/status/[0-9]+(?:/(?:photo|video)/[0-9]+)?|i/(?:web/)?status/[0-9]+)/?$"
    assert rewrite("https://twitter.com/person/status/1234567890123456789?s=20") == "https://x.milkhaus.net/person/status/1234567890123456789"
    assert rewrite("https://x.com/person/status/1234567890123456789/photo/2") == "https://x.milkhaus.net/person/status/1234567890123456789/photo/2"
    assert rewrite("https://x.com/person") is None


if __name__ == "__main__":
    run_checks()
    print("3 rewrite examples passed")
