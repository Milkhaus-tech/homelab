import asyncio
import html
import logging
import os
import re
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
import yt_dlp
from PIL import Image


LOG = logging.getLogger("igembed")
SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,32}$")
POST_RE = re.compile(
    r"^/(?:(?:reel|reels|p|tv)/([A-Za-z0-9_-]{5,32})|"
    r"[A-Za-z0-9._]+/(?:reel|reels|p|tv)/([A-Za-z0-9_-]{5,32}))/?$"
)
BOT_MARKERS = (
    "discordbot", "twitterbot", "facebookexternalhit", "telegrambot",
    "whatsapp", "slackbot", "linkedinbot", "mastodon", "iframely",
    "embedly", "googlebot", "bot",
)
CDN_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
FAILURE_DESCRIPTIONS = {
    "auth": "Instagram won't show this post without a login",
    "gone": "this post is unavailable",
    "error": "couldn't fetch this post",
}


class Extractor:
    def __init__(self, cookies_file=None):
        self.cookies_file = cookies_file

    def extract(self, shortcode):
        url = f"https://www.instagram.com/reel/{shortcode}/"
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": False,
            "format": "best[acodec!=none][vcodec!=none]/best",
            "ignore_no_formats_error": True,
        }
        if self.cookies_file:
            options["cookiefile"] = self.cookies_file
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
        item = _first_media(info)
        if item and item.get("url"):
            return _result_from_info(item)
        entries = (info.get("entries") or ()) if info.get("_type") == "playlist" else (info,)
        images = [entry.get("thumbnail") for entry in entries if entry and entry.get("thumbnail")]
        if not images:
            raise RuntimeError("no media found")
        fallback = next((entry for entry in entries if entry), {})
        metadata = {
            key: info.get(key) if info.get(key) is not None else fallback.get(key)
            for key in (
                "title", "uploader", "channel", "uploader_id", "description",
                "like_count", "comment_count",
            )
        }
        return {
            "video_url": None,
            "thumbnail_url": images[0],
            "images": images,
            "width": None,
            "height": None,
            **metadata,
        }


def _first_media(info):
    if not info:
        return None
    if info.get("_type") == "playlist":
        for entry in info.get("entries") or ():
            if entry and entry.get("url"):
                return entry
        return None
    return info


def _result_from_info(info):
    width = info.get("width")
    height = info.get("height")
    if width is None or height is None:
        sized_formats = [
            item for item in info.get("formats") or ()
            if item.get("width") is not None and item.get("height") is not None
        ]
        if sized_formats:
            dimensions = max(sized_formats, key=lambda item: item["width"] * item["height"])
            width = width or dimensions["width"]
            height = height or dimensions["height"]
    return {
        "video_url": info["url"],
        "thumbnail_url": info.get("thumbnail"),
        "width": width,
        "height": height,
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "channel": info.get("channel"),
        "uploader_id": info.get("uploader_id"),
        "description": info.get("description"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
    }


class ExtractionCache:
    def __init__(self, extractor):
        self.extractor = extractor
        self.cache = {}
        self.inflight = {}
        self.semaphore = asyncio.Semaphore(3)

    async def get(self, shortcode):
        now = time.monotonic()
        cached = self.cache.get(shortcode)
        if cached and cached[0] > now:
            return cached[1]

        future = self.inflight.get(shortcode)
        if future is not None:
            return await asyncio.shield(future)

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.inflight[shortcode] = future
        started = time.monotonic()
        try:
            async with self.semaphore:
                try:
                    result = await asyncio.to_thread(self.extractor.extract, shortcode)
                except Exception as exc:
                    LOG.warning(
                        "extraction id=%s outcome=failure ms=%d error=%s",
                        shortcode, (time.monotonic() - started) * 1000, exc,
                    )
                    result = _classify_failure(str(exc))
            ttl = 300 if _failed(result) else 3600
            self.cache[shortcode] = (time.monotonic() + ttl, result)
            self._trim()
            if not _failed(result):
                LOG.info(
                    "extraction id=%s outcome=success ms=%d",
                    shortcode, (time.monotonic() - started) * 1000,
                )
            future.set_result(result)
            return result
        finally:
            self.inflight.pop(shortcode, None)
            if not future.done():
                future.cancel()

    def _trim(self):
        if len(self.cache) <= 2000:
            return
        now = time.monotonic()
        self.cache = {key: value for key, value in self.cache.items() if value[0] > now}
        while len(self.cache) > 2000:
            oldest = min(self.cache, key=lambda key: self.cache[key][0])
            del self.cache[oldest]


def _valid_shortcode(value):
    return bool(SHORTCODE_RE.fullmatch(value))


def _classify_failure(message):
    message = message.lower()
    if any(marker in message for marker in (
        "login", "cookies", "empty media response", "not granting access", "rate-limit",
    )):
        return "auth"
    if any(marker in message for marker in (
        "not found", "does not exist", "unavailable", "removed", "private",
    )):
        return "gone"
    return "error"


def _failed(result):
    return isinstance(result, str)


def _escape(value):
    return html.escape(str(value), quote=True)


def render_og(shortcode, result, base_url):
    instagram_url = f"https://www.instagram.com/reel/{shortcode}/"
    if _failed(result):
        description = FAILURE_DESCRIPTIONS[result]
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta property="og:title" content="Instagram">'
            f'<meta property="og:description" content="{_escape(description)}">'
            f'<meta http-equiv="refresh" content="0; url={_escape(instagram_url)}">'
            '</head><body></body></html>'
        )

    username = result.get("channel") or result.get("uploader_id") or result.get("uploader") or "Instagram"
    username = username if str(username).startswith("@") else f"@{username}"
    description = (result.get("description") or "")[:300]
    video_url = f"{base_url}/video/{shortcode}"
    image_url = f"{base_url}/image/{shortcode}"
    counts = []
    if result.get("like_count") is not None:
        counts.append(f"❤️ {result['like_count']:,}")
    if result.get("comment_count") is not None:
        counts.append(f"💬 {result['comment_count']:,}")
    oembed_query = urlencode({"text": "  ".join(counts), "url": instagram_url})
    is_video = bool(result.get("video_url"))
    if not is_video and len(result.get("images") or ()) > 1:
        description += f" ({len(result['images'])} photos)"
    tags = [
        '<!DOCTYPE html><html><head><meta charset="utf-8">',
        '<meta name="theme-color" content="#E1306C">',
        '<meta property="og:site_name" content="ig.milkhaus.net">',
        f'<meta property="og:type" content="{"video.other" if is_video else "website"}">',
        f'<meta property="og:url" content="{_escape(instagram_url)}">',
        f'<meta property="og:title" content="{_escape(username)}">',
        f'<meta property="og:description" content="{_escape(description)}">',
        f'<meta property="og:image" content="{_escape(image_url)}">',
    ]
    if is_video:
        tags.extend([
            f'<meta property="og:video" content="{_escape(video_url)}">',
            f'<meta property="og:video:secure_url" content="{_escape(video_url)}">',
            '<meta property="og:video:type" content="video/mp4">',
        ])
        if result.get("width") is not None:
            tags.append(f'<meta property="og:video:width" content="{_escape(result["width"])}">')
        if result.get("height") is not None:
            tags.append(f'<meta property="og:video:height" content="{_escape(result["height"])}">')
        tags.extend([
            '<meta name="twitter:card" content="player">',
            f'<meta name="twitter:title" content="{_escape(username)}">',
            f'<meta name="twitter:player:stream" content="{_escape(video_url)}">',
            '<meta name="twitter:player:stream:content_type" content="video/mp4">',
        ])
        if result.get("width") is not None:
            tags.append(f'<meta name="twitter:player:width" content="{_escape(result["width"])}">')
        if result.get("height") is not None:
            tags.append(f'<meta name="twitter:player:height" content="{_escape(result["height"])}">')
    else:
        tags.append('<meta name="twitter:card" content="summary_large_image">')
        if result.get("width") is not None:
            tags.append(f'<meta property="og:image:width" content="{_escape(result["width"])}">')
        if result.get("height") is not None:
            tags.append(f'<meta property="og:image:height" content="{_escape(result["height"])}">')
    tags.extend([
        f'<link rel="alternate" href="{_escape(base_url)}/oembed?{_escape(oembed_query)}" '
        f'type="application/json+oembed" title="{_escape(username)}">',
        f'<meta http-equiv="refresh" content="0; url={_escape(instagram_url)}">',
        '</head><body></body></html>',
    ])
    return "\n".join(tags)


async def post_route(request):
    match = POST_RE.fullmatch(request.path)
    if not match:
        raise web.HTTPNotFound()
    shortcode = match.group(1) or match.group(2)
    if not _valid_shortcode(shortcode):
        raise web.HTTPNotFound()
    ua = request.headers.get("User-Agent", "")
    media = "Range" in request.headers or "Icy-MetaData" in request.headers
    bot = any(marker in ua.lower() for marker in BOT_MARKERS)
    classification = "media" if media else "bot" if bot else "human"
    LOG.info("post id=%s class=%s ua=%r", shortcode, classification, ua)
    if media:
        result = await request.app["extractions"].get(shortcode)
        kind = "image" if not _failed(result) and not result.get("video_url") else "video"
        raise web.HTTPFound(f"/{kind}/{shortcode}")
    if bot:
        result = await request.app["extractions"].get(shortcode)
        page = render_og(shortcode, result, request.app["base_url"])
        headers = {"X-Igembed-Error": result} if _failed(result) else None
        return web.Response(text=page, content_type="text/html", headers=headers)
    target = f"https://www.instagram.com{request.path}"
    if request.query_string:
        target += f"?{request.query_string}"
    raise web.HTTPFound(target)


async def proxy(request, kind):
    shortcode = request.match_info["shortcode"]
    if not _valid_shortcode(shortcode):
        raise web.HTTPNotFound()
    result = await request.app["extractions"].get(shortcode)
    if _failed(result):
        return web.Response(
            status=502, text=f"{kind} unavailable", headers={"X-Igembed-Error": result},
        )
    upstream_url = result.get(f"{kind}_url")
    if not upstream_url:
        return web.Response(status=502, text=f"{kind} unavailable")
    LOG.info("proxy id=%s kind=%s method=%s", shortcode, kind, request.method)
    headers = {}
    if "Range" in request.headers:
        headers["Range"] = request.headers["Range"]
    try:
        session = request.app["client_session"]
        upstream_method = "GET" if request.method == "HEAD" else request.method
        async with session.request(upstream_method, upstream_url, headers=headers) as upstream:
            if upstream.status not in (200, 206):
                return web.Response(status=502, text="upstream failure")
            response_headers = {"Cache-Control": "public, max-age=3600"}
            for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                if name in upstream.headers:
                    response_headers[name] = upstream.headers[name]
            response_headers.setdefault("Content-Type", "video/mp4" if kind == "video" else "image/jpeg")
            response = web.StreamResponse(status=upstream.status, headers=response_headers)
            await response.prepare(request)
            if request.method != "HEAD":
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await response.write(chunk)
            await response.write_eof()
            return response
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        LOG.warning("proxy id=%s kind=%s error=%s", shortcode, kind, exc)
        return web.Response(status=502, text="upstream failure")


async def video_route(request):
    return await proxy(request, "video")


async def image_route(request):
    shortcode = request.match_info["shortcode"]
    result = await request.app["extractions"].get(shortcode)
    if _failed(result):
        return web.Response(
            status=502, text="image unavailable", headers={"X-Igembed-Error": result},
        )
    images = result.get("images")
    if not images or len(images) == 1:
        return await proxy(request, "thumbnail")
    lock = request.app["grid_locks"].setdefault(shortcode, asyncio.Lock())
    try:
        async with lock:
            if result.get("grid") is None:
                blobs = await asyncio.gather(*[
                    _fetch_image(request.app["client_session"], url) for url in images[:4]
                ])
                grid, width, height = await asyncio.to_thread(_make_grid, blobs)
                result["grid"] = grid
                result["width"], result["height"] = width, height
        request.app["grid_locks"].pop(shortcode, None)
        body = result["grid"]
        return web.Response(
            body=b"" if request.method == "HEAD" else body,
            headers={
                "Content-Type": "image/jpeg",
                "Content-Length": str(len(body)),
                "Cache-Control": "public, max-age=3600",
            },
        )
    except Exception as exc:
        LOG.warning("grid id=%s error=%s; falling back", shortcode, exc)
        return await proxy(request, "thumbnail")


async def _fetch_image(session, url):
    timeout = aiohttp.ClientTimeout(total=10)
    async with session.get(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"image upstream status {response.status}")
        length = response.content_length
        if length is not None and length > 10 * 1024 * 1024:
            raise RuntimeError("image exceeds 10 MB")
        data = bytearray()
        async for chunk in response.content.iter_chunked(64 * 1024):
            data.extend(chunk)
            if len(data) > 10 * 1024 * 1024:
                raise RuntimeError("image exceeds 10 MB")
        return bytes(data)


def _make_grid(blobs):
    images = []
    for blob in blobs:
        with Image.open(BytesIO(blob)) as source:
            image = source.convert("RGB")
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            images.append(image.copy())
    rows = 1 if len(images) == 2 else 2
    canvas = Image.new("RGB", (2048, rows * 1024), "white")
    for index, image in enumerate(images):
        x = (index % 2) * 1024 + (1024 - image.width) // 2
        y = (index // 2) * 1024 + (1024 - image.height) // 2
        canvas.paste(image, (x, y))
    output = BytesIO()
    canvas.save(output, format="JPEG", quality=85)
    return output.getvalue(), canvas.width, canvas.height


async def oembed(request):
    return web.json_response({
        "author_name": request.query.get("text", ""),
        "author_url": request.query.get("url", ""),
        "provider_name": "ig.milkhaus.net",
        "provider_url": "https://ig.milkhaus.net",
        "title": "Instagram",
        "type": "link",
        "version": "1.0",
    })


async def root(_request):
    return web.Response(
        text="Replace instagram.com with ig.milkhaus.net in a reel link and Discord will embed the video.",
        content_type="text/html",
    )


async def healthz(_request):
    return web.Response(text="ok")


async def _make_session(app):
    if app.get("client_session") is None:
        # No total cap: a video streams for as long as it takes, but a stalled CDN gives up.
        app["client_session"] = aiohttp.ClientSession(
            headers={"User-Agent": CDN_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30),
        )
        app["owns_session"] = True


async def _close_session(app):
    if app.get("owns_session"):
        await app["client_session"].close()


def create_app(extractor=None, base_url=None, client_session=None):
    app = web.Application()
    app["base_url"] = (base_url or os.getenv("PUBLIC_BASE_URL", "https://ig.milkhaus.net")).rstrip("/")
    app["extractions"] = ExtractionCache(extractor or Extractor(_cookies_file()))
    app["client_session"] = client_session
    app["owns_session"] = False
    app["grid_locks"] = {}
    app.on_startup.append(_make_session)
    app.on_cleanup.append(_close_session)
    code = r"{shortcode:[A-Za-z0-9_-]{5,32}}"
    app.router.add_get("/", root)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/oembed", oembed)
    app.router.add_get(f"/video/{code}", video_route, allow_head=False)
    app.router.add_head(f"/video/{code}", video_route)
    app.router.add_get(f"/image/{code}", image_route, allow_head=False)
    app.router.add_head(f"/image/{code}", image_route)
    app.router.add_route("*", "/{tail:.*}", post_route)
    return app


def _cookies_file():
    value = os.getenv("IG_COOKIES_FILE")
    return value if value and Path(value).is_file() else None


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cookies = _cookies_file()
    LOG.info("startup cookies=%s", "enabled" if cookies else "disabled")
    app = create_app(extractor=Extractor(cookies))
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
