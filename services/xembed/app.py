import asyncio
import html
import inspect
import logging
import math
import os
import re
import time
from io import BytesIO
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
import yt_dlp
from PIL import Image


LOG = logging.getLogger("xembed")
ID_RE = re.compile(r"^[0-9]+$")
POST_RE = re.compile(
    r"^/(?:([A-Za-z0-9_]{1,15})/status/([0-9]+)(?:/(?:photo|video)/[0-9]+)?|"
    r"i/(?:web/)?status/([0-9]+))/?$"
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
    "gone": "this post is unavailable",
    "down": "X isn't answering right now",
    "error": "couldn't fetch this post",
}


def _base36_digit(value):
    return "0123456789abcdefghijklmnopqrstuvwxyz"[value]


def tweet_token(tweet_id):
    """Equivalent to JS ((Number(id) / 1e15) * Math.PI).toString(36), stripped."""
    value = float(tweet_id) / 1e15 * math.pi
    integer = int(value)
    integer_text = "0"
    if integer:
        digits = []
        while integer:
            integer, digit = divmod(integer, 36)
            digits.append(_base36_digit(digit))
        integer_text = "".join(reversed(digits))
    fraction = value - int(value)
    digits = []
    # V8's base-36 rendering carries 11 significant base-36 digits here.
    # Keep leading fractional zeroes for place value, then round the last digit.
    for _ in range(40):
        fraction *= 36
        digit = int(fraction)
        digits.append(_base36_digit(digit))
        fraction -= digit
    integer_significant = len(integer_text.lstrip("0"))
    leading = 0
    if not integer_significant:
        while leading < len(digits) and digits[leading] == "0":
            leading += 1
    keep = leading + 11 - integer_significant
    kept = [int(char, 36) for char in digits[:keep]]
    if keep < len(digits) and int(digits[keep], 36) >= 18:
        index = len(kept) - 1
        while index >= 0:
            kept[index] += 1
            if kept[index] < 36:
                break
            kept[index] = 0
            index -= 1
    chosen = "".join(_base36_digit(digit) for digit in kept)
    return (integer_text + "." + chosen).replace(".", "").replace("0", "")


class Extractor:
    async def extract(self, tweet_id):
        url = "https://cdn.syndication.twimg.com/tweet-result"
        params = {"id": tweet_id, "token": tweet_token(tweet_id)}
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 404:
                    return await self._rescue(tweet_id, "gone")
                if response.status >= 500:
                    return "down"
                if response.status != 200:
                    return "error"
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return "down"
        except Exception as exc:
            LOG.warning("syndication id=%s error=%s", tweet_id, exc)
            return "error"
        if data.get("__typename") == "TweetTombstone":
            return await self._rescue(tweet_id, "gone")
        if data.get("__typename") != "Tweet":
            return "error"
        result = _tweet_result(tweet_id, data)
        if result.get("has_video") and not result.get("video_url"):
            rescued = await self._rescue(tweet_id, None)
            if isinstance(rescued, dict):
                result.update({key: value for key, value in rescued.items() if value is not None})
        return result

    async def _rescue(self, tweet_id, fallback):
        try:
            result = await asyncio.to_thread(self._ytdlp, tweet_id)
            return result or fallback
        except Exception as exc:
            if "no video could be found" in str(exc).lower():
                return fallback
            LOG.warning("yt-dlp id=%s error=%s", tweet_id, exc)
            return fallback if fallback else "error"

    @staticmethod
    def _ytdlp(tweet_id):
        options = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "format": "best[ext=mp4][acodec!=none][vcodec!=none]/best",
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"https://x.com/i/status/{tweet_id}", download=False)
        if not info or not info.get("url"):
            return None
        return {
            "video_url": info["url"], "thumbnail_url": info.get("thumbnail"),
            "width": info.get("width"), "height": info.get("height"),
            "has_video": True,
        }


def _visible_text(tweet):
    text = tweet.get("text") or ""
    bounds = tweet.get("display_text_range")
    if isinstance(bounds, list) and len(bounds) == 2:
        text = text[bounds[0]:bounds[1]]
    return text.strip()


def _tweet_result(tweet_id, tweet):
    user = tweet.get("user") or {}
    photos = []
    video = None
    poster = None
    width = height = None
    has_video = False
    for media in tweet.get("mediaDetails") or ():
        kind = media.get("type")
        info = media.get("original_info") or {}
        if kind == "photo":
            if media.get("media_url_https"):
                photos.append(media["media_url_https"])
            width, height = width or info.get("width"), height or info.get("height")
        elif kind in ("video", "animated_gif"):
            has_video = True
            poster = poster or media.get("media_url_https")
            width, height = info.get("width"), info.get("height")
            variants = [v for v in (media.get("video_info") or {}).get("variants") or ()
                        if v.get("content_type") == "video/mp4" and v.get("url")]
            if variants:
                video = max(variants, key=lambda v: v.get("bitrate") or 0)["url"]
    quote = tweet.get("quoted_tweet")
    description = _visible_text(tweet)
    if isinstance(quote, dict) and quote.get("__typename", "Tweet") == "Tweet":
        q_user = quote.get("user") or {}
        suffix = f"\n\n↪ @{q_user.get('screen_name', '')}: {_visible_text(quote)}"
        description = (description + suffix)[:300]
    return {
        "id": tweet_id, "username": user.get("screen_name") or "i",
        "name": user.get("name") or user.get("screen_name") or "X",
        "description": description[:300], "avatar_url": user.get("profile_image_url_https"),
        "like_count": tweet.get("favorite_count"),
        "comment_count": tweet.get("conversation_count"),
        "retweet_count": tweet.get("retweet_count"),
        "video_url": video, "thumbnail_url": poster or (photos[0] if photos else None),
        "images": photos, "width": width, "height": height, "has_video": has_video,
    }


class ExtractionCache:
    def __init__(self, extractor):
        self.extractor, self.cache, self.inflight = extractor, {}, {}
        self.semaphore = asyncio.Semaphore(3)

    async def get(self, tweet_id):
        now = time.monotonic()
        cached = self.cache.get(tweet_id)
        if cached and cached[0] > now:
            return cached[1]
        if tweet_id in self.inflight:
            return await asyncio.shield(self.inflight[tweet_id])
        future = asyncio.get_running_loop().create_future()
        self.inflight[tweet_id] = future
        try:
            async with self.semaphore:
                try:
                    result = self.extractor.extract(tweet_id)
                    result = await result if inspect.isawaitable(result) else result
                except Exception as exc:
                    LOG.warning("extraction id=%s error=%s", tweet_id, exc)
                    result = "error"
            self.cache[tweet_id] = (time.monotonic() + (300 if _failed(result) else 3600), result)
            self._trim()
            future.set_result(result)
            return result
        finally:
            self.inflight.pop(tweet_id, None)
            if not future.done():
                future.cancel()

    def _trim(self):
        if len(self.cache) <= 2000:
            return
        now = time.monotonic()
        self.cache = {k: v for k, v in self.cache.items() if v[0] > now}
        while len(self.cache) > 2000:
            del self.cache[min(self.cache, key=lambda k: self.cache[k][0])]


def _failed(result):
    return isinstance(result, str)


def _escape(value):
    return html.escape(str(value), quote=True)


def _post_url(result, tweet_id):
    return f"https://x.com/{result.get('username') or 'i'}/status/{tweet_id}"


def render_og(tweet_id, result, base_url):
    target = f"https://x.com/i/status/{tweet_id}" if _failed(result) else _post_url(result, tweet_id)
    if _failed(result):
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta property="og:title" content="X">'
            f'<meta property="og:description" content="{_escape(FAILURE_DESCRIPTIONS[result])}">'
            f'<meta http-equiv="refresh" content="0; url={_escape(target)}">'
            '</head><body></body></html>'
        )
    title = f"{result['name']} (@{result['username']})"
    video_url, image_url = f"{base_url}/video/{tweet_id}", f"{base_url}/image/{tweet_id}"
    is_video = bool(result.get("video_url"))
    has_photos = bool(result.get("images"))
    og_image = image_url if is_video or has_photos else result.get("avatar_url") or image_url
    counts = []
    for key, icon in (("like_count", "❤️"), ("retweet_count", "🔁"), ("comment_count", "💬")):
        if result.get(key) is not None:
            counts.append(f"{icon} {result[key]:,}")
    oembed_query = urlencode({"text": "  ".join(counts), "url": target})
    tags = [
        '<!DOCTYPE html><html><head><meta charset="utf-8">',
        '<meta name="theme-color" content="#000000">',
        '<meta property="og:site_name" content="x.milkhaus.net">',
        f'<meta property="og:type" content="{"video.other" if is_video else "website"}">',
        f'<meta property="og:url" content="{_escape(target)}">',
        f'<meta property="og:title" content="{_escape(title)}">',
        f'<meta property="og:description" content="{_escape(result.get("description") or "")}">',
        f'<meta property="og:image" content="{_escape(og_image)}">',
    ]
    if is_video:
        tags += [
            f'<meta property="og:video" content="{_escape(video_url)}">',
            f'<meta property="og:video:secure_url" content="{_escape(video_url)}">',
            '<meta property="og:video:type" content="video/mp4">',
        ]
        if result.get("width") is not None:
            tags.append(f'<meta property="og:video:width" content="{result["width"]}">')
        if result.get("height") is not None:
            tags.append(f'<meta property="og:video:height" content="{result["height"]}">')
        tags += [
            '<meta name="twitter:card" content="player">',
            f'<meta name="twitter:title" content="{_escape(title)}">',
            f'<meta name="twitter:player:stream" content="{_escape(video_url)}">',
            '<meta name="twitter:player:stream:content_type" content="video/mp4">',
        ]
        if result.get("width") is not None:
            tags.append(f'<meta name="twitter:player:width" content="{result["width"]}">')
        if result.get("height") is not None:
            tags.append(f'<meta name="twitter:player:height" content="{result["height"]}">')
    else:
        tags.append(f'<meta name="twitter:card" content="{"summary_large_image" if has_photos else "summary"}">')
        if has_photos and result.get("width") is not None:
            tags.append(f'<meta property="og:image:width" content="{result["width"]}">')
        if has_photos and result.get("height") is not None:
            tags.append(f'<meta property="og:image:height" content="{result["height"]}">')
    tags += [
        f'<link rel="alternate" href="{_escape(base_url)}/oembed?{_escape(oembed_query)}" type="application/json+oembed" title="{_escape(title)}">',
        f'<meta http-equiv="refresh" content="0; url={_escape(target)}">',
        '</head><body></body></html>',
    ]
    return "\n".join(tags)


async def post_route(request):
    match = POST_RE.fullmatch(request.path)
    if not match:
        raise web.HTTPNotFound()
    handle, tweet_id = match.group(1), match.group(2) or match.group(3)
    ua = request.headers.get("User-Agent", "")
    media = "Range" in request.headers or "Icy-MetaData" in request.headers
    bot = any(marker in ua.lower() for marker in BOT_MARKERS)
    if media:
        result = await request.app["extractions"].get(tweet_id)
        kind = "video" if _failed(result) or result.get("video_url") else "image"
        raise web.HTTPFound(f"/{kind}/{tweet_id}")
    if bot:
        result = await request.app["extractions"].get(tweet_id)
        headers = {"X-Xembed-Error": result} if _failed(result) else None
        return web.Response(text=render_og(tweet_id, result, request.app["base_url"]), content_type="text/html", headers=headers)
    target = f"https://x.com{request.path}"
    if request.query_string:
        target += f"?{request.query_string}"
    raise web.HTTPFound(target)


async def _stream(request, upstream_url, default_type):
    headers = {"Range": request.headers["Range"]} if "Range" in request.headers else {}
    try:
        method = "GET" if request.method == "HEAD" else request.method
        async with request.app["client_session"].request(method, upstream_url, headers=headers) as upstream:
            if upstream.status not in (200, 206):
                return web.Response(status=502, text="upstream failure")
            outgoing = {"Cache-Control": "public, max-age=3600"}
            for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                if name in upstream.headers:
                    outgoing[name] = upstream.headers[name]
            outgoing.setdefault("Content-Type", default_type)
            response = web.StreamResponse(status=upstream.status, headers=outgoing)
            await response.prepare(request)
            if request.method != "HEAD":
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await response.write(chunk)
            await response.write_eof()
            return response
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return web.Response(status=502, text="upstream failure")


async def video_route(request):
    tweet_id = request.match_info["id"]
    result = await request.app["extractions"].get(tweet_id)
    if _failed(result):
        return web.Response(status=502, text="video unavailable", headers={"X-Xembed-Error": result})
    if not result.get("video_url"):
        return web.Response(status=502, text="video unavailable")
    return await _stream(request, result["video_url"], "video/mp4")


async def image_route(request):
    tweet_id = request.match_info["id"]
    result = await request.app["extractions"].get(tweet_id)
    if _failed(result):
        return web.Response(status=502, text="image unavailable", headers={"X-Xembed-Error": result})
    images = [result.get("thumbnail_url")] if result.get("video_url") else result.get("images") or []
    images = [url for url in images if url]
    if not images:
        return web.Response(status=502, text="image unavailable")
    if len(images) == 1:
        return await _stream(request, images[0], "image/jpeg")
    lock = request.app["grid_locks"].setdefault(tweet_id, asyncio.Lock())
    try:
        async with lock:
            if result.get("grid") is None:
                blobs = await asyncio.gather(*[_fetch_image(request.app["client_session"], u) for u in images[:4]])
                result["grid"], result["width"], result["height"] = await asyncio.to_thread(_make_grid, blobs)
        body = result["grid"]
        return web.Response(body=b"" if request.method == "HEAD" else body, headers={
            "Content-Type": "image/jpeg", "Content-Length": str(len(body)),
            "Cache-Control": "public, max-age=3600",
        })
    except Exception as exc:
        LOG.warning("grid id=%s error=%s", tweet_id, exc)
        return await _stream(request, images[0], "image/jpeg")
    finally:
        request.app["grid_locks"].pop(tweet_id, None)


async def individual_image_route(request):
    result = await request.app["extractions"].get(request.match_info["id"])
    if _failed(result):
        return web.Response(status=502, text="image unavailable", headers={"X-Xembed-Error": result})
    images = [result.get("thumbnail_url")] if result.get("video_url") else result.get("images") or []
    index = int(request.match_info["number"])
    if index > len(images) or not images[index - 1]:
        raise web.HTTPNotFound()
    return await _stream(request, images[index - 1], "image/jpeg")


async def api_route(request):
    tweet_id = request.match_info["id"]
    result = await request.app["extractions"].get(tweet_id)
    headers = {"Cache-Control": "no-store"}
    if _failed(result):
        headers["X-Xembed-Error"] = result
        return web.json_response({"ok": False, "error": result}, headers=headers)
    base = request.app["base_url"]
    is_video = bool(result.get("video_url"))
    images = [result.get("thumbnail_url")] if is_video else result.get("images") or []
    return web.json_response({
        "ok": True, "kind": "video" if is_video else "photo" if images else "text",
        "id": tweet_id, "post_url": _post_url(result, tweet_id),
        "username": result.get("username"), "name": result.get("name"),
        "description": result.get("description") or "", "like_count": result.get("like_count"),
        "comment_count": result.get("comment_count"), "retweet_count": result.get("retweet_count"),
        "video_url": f"{base}/video/{tweet_id}" if is_video else None,
        "images": [f"{base}/image/{tweet_id}/{n}" for n in range(1, len(images) + 1)],
    }, headers=headers)


async def _fetch_image(session, url):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
        if response.status != 200:
            raise RuntimeError(f"image upstream status {response.status}")
        data = await response.read()
        if len(data) > 10 * 1024 * 1024:
            raise RuntimeError("image exceeds 10 MB")
        return data


def _make_grid(blobs):
    columns = 2
    cell = 1024
    rows = -(-len(blobs) // columns)
    canvas = Image.new("RGB", (columns * cell, rows * cell), "white")
    for index, blob in enumerate(blobs):
        with Image.open(BytesIO(blob)) as source:
            image = source.convert("RGB")
            image.thumbnail((cell, cell), Image.Resampling.LANCZOS)
            x = index % columns * cell + (cell - image.width) // 2
            y = index // columns * cell + (cell - image.height) // 2
            canvas.paste(image, (x, y))
    output = BytesIO()
    canvas.save(output, "JPEG", quality=85)
    return output.getvalue(), canvas.width, canvas.height


async def oembed(request):
    return web.json_response({
        "author_name": request.query.get("text", ""), "author_url": request.query.get("url", ""),
        "provider_name": "x.milkhaus.net", "provider_url": "https://x.milkhaus.net",
        "title": "X", "type": "link", "version": "1.0",
    })


async def root(_request):
    return web.Response(text="Replace x.com with x.milkhaus.net in a post URL and Discord will embed its media.", content_type="text/html")


async def healthz(_request):
    return web.Response(text="ok")


async def _make_session(app):
    if app.get("client_session") is None:
        app["client_session"] = aiohttp.ClientSession(headers={"User-Agent": CDN_USER_AGENT}, timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30))
        app["owns_session"] = True
    if isinstance(app["extractions"].extractor, Extractor):
        app["extractions"].extractor.session = app["client_session"]


async def _close_session(app):
    if app.get("owns_session"):
        await app["client_session"].close()


def create_app(extractor=None, base_url=None, client_session=None):
    app = web.Application()
    app["base_url"] = (base_url or os.getenv("PUBLIC_BASE_URL", "https://x.milkhaus.net")).rstrip("/")
    app["extractions"] = ExtractionCache(extractor or Extractor())
    app["client_session"], app["owns_session"], app["grid_locks"] = client_session, False, {}
    app.on_startup.append(_make_session)
    app.on_cleanup.append(_close_session)
    code = r"{id:[0-9]+}"
    app.router.add_get("/", root)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/oembed", oembed)
    app.router.add_get(f"/api/{code}", api_route)
    for prefix, handler in (("video", video_route), ("image", image_route)):
        app.router.add_get(f"/{prefix}/{code}", handler, allow_head=False)
        app.router.add_head(f"/{prefix}/{code}", handler)
    number = r"{number:[1-9][0-9]*}"
    app.router.add_get(f"/image/{code}/{number}", individual_image_route, allow_head=False)
    app.router.add_head(f"/image/{code}/{number}", individual_image_route)
    app.router.add_route("*", "/{tail:.*}", post_route)
    return app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    web.run_app(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
