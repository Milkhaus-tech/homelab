import asyncio
from io import BytesIO

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from app import BOT_MARKERS, POST_RE, _make_grid, create_app, tweet_token
from test_page import run_checks as run_page_checks


ID = "1732824684683784516"
BASE = "https://example.test"
TESTS = 0


def check(value):
    global TESTS
    assert value
    TESTS += 1


class FakeExtractor:
    def __init__(self, result):
        self.result = result

    async def extract(self, tweet_id):
        check(tweet_id in (ID, "20"))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def result(**changes):
    base = {
        "id": ID, "username": "SpaceX", "name": "SpaceX",
        "description": 'Launch & "landing"', "avatar_url": "https://cdn.invalid/avatar.jpg",
        "like_count": 100, "comment_count": 20, "retweet_count": 30,
        "video_url": "https://cdn.invalid/video.mp4",
        "thumbnail_url": "https://cdn.invalid/poster.jpg", "images": [],
        "width": 1280, "height": 720, "has_video": True,
    }
    base.update(changes)
    return base


def jpeg(size, color):
    output = BytesIO()
    Image.new("RGB", size, color).save(output, "JPEG")
    return output.getvalue()


async def api_and_routes():
    video = result()
    async with TestClient(TestServer(create_app(FakeExtractor(video), BASE))) as client:
        response = await client.get("/")
        check(response.status == 200 and "<title>TETO ZONE — X / Twitter embeds</title>" in await response.text())
        check((await client.head("/")).status == 200)
        response = await client.get("/assets/og.png")
        check(response.status == 200 and response.headers["Content-Type"] == "image/png")
        check((await client.get("/assets/nope")).status == 404)
        check((await client.get("/assets/../app.py")).status == 404)

        response = await client.get(f"/api/{ID}")
        payload = await response.json()
        check(response.status == 200 and response.headers["Cache-Control"] == "no-store")
        check(payload == {
            "ok": True, "kind": "video", "id": ID,
            "post_url": f"https://x.com/SpaceX/status/{ID}", "username": "SpaceX", "name": "SpaceX",
            "description": 'Launch & "landing"', "like_count": 100, "comment_count": 20,
            "retweet_count": 30, "video_url": f"{BASE}/video/{ID}",
            "images": [f"{BASE}/image/{ID}/1"],
        })
        response = await client.get(f"/SpaceX/status/{ID}?s=20", headers={"User-Agent": "Discordbot/2"})
        body = await response.text()
        check(f'<meta property="og:video" content="{BASE}/video/{ID}">' in body)
        check('<meta name="twitter:card" content="player">' in body)
        check("Launch &amp; &quot;landing&quot;" in body)
        check("%E2%9D%A4%EF%B8%8F+100" in body and "%F0%9F%94%81+30" in body and "%F0%9F%92%AC+20" in body)
        response = await client.get(f"/SpaceX/status/{ID}?s=20", headers={"User-Agent": "Mozilla"}, allow_redirects=False)
        check(response.status == 302 and response.headers["Location"] == f"https://x.com/SpaceX/status/{ID}?s=20")
        for headers in ({"Range": "bytes=0-1"}, {"Icy-MetaData": "1"}):
            response = await client.get(f"/i/status/{ID}", headers=headers, allow_redirects=False)
            check(response.status == 302 and response.headers["Location"] == f"/video/{ID}")

    photos = result(video_url=None, has_video=False, thumbnail_url="https://cdn.invalid/1.jpg",
                    images=[f"https://cdn.invalid/{n}.jpg" for n in range(1, 4)], width=1600, height=900)
    async with TestClient(TestServer(create_app(FakeExtractor(photos), BASE))) as client:
        payload = await (await client.get(f"/api/{ID}")).json()
        check(payload["kind"] == "photo" and len(payload["images"]) == 3 and payload["video_url"] is None)
        body = await (await client.get(f"/SpaceX/status/{ID}/photo/2", headers={"User-Agent": "Slackbot"})).text()
        check('<meta name="twitter:card" content="summary_large_image">' in body and "og:video" not in body)
        response = await client.get(f"/i/web/status/{ID}", headers={"Range": "bytes=0-1"}, allow_redirects=False)
        check(response.headers["Location"] == f"/image/{ID}")

    text = result(video_url=None, has_video=False, thumbnail_url=None, images=[], width=None, height=None)
    async with TestClient(TestServer(create_app(FakeExtractor(text), BASE))) as client:
        payload = await (await client.get(f"/api/{ID}")).json()
        check(payload["kind"] == "text" and payload["images"] == [])
        body = await (await client.get(f"/i/status/{ID}", headers={"User-Agent": "Twitterbot"})).text()
        check('<meta name="twitter:card" content="summary">' in body)
        check('<meta property="og:image" content="https://cdn.invalid/avatar.jpg">' in body)

    quoted = result(description="Main\n\n↪ @jack: quoted words")
    async with TestClient(TestServer(create_app(FakeExtractor(quoted), BASE))) as client:
        payload = await (await client.get(f"/api/{ID}")).json()
        check(payload["description"] == "Main\n\n↪ @jack: quoted words")


async def failures():
    for failure in ("gone", "down", "error"):
        async with TestClient(TestServer(create_app(FakeExtractor(failure), BASE))) as client:
            response = await client.get(f"/api/{ID}")
            check(await response.json() == {"ok": False, "error": failure})
            check(response.headers["X-Xembed-Error"] == failure)
            response = await client.get(f"/i/status/{ID}", headers={"User-Agent": "Discordbot"})
            check(response.status == 200 and response.headers["X-Xembed-Error"] == failure)
            expected = {"gone": "this post is unavailable", "down": "X isn&#x27;t answering right now", "error": "couldn&#x27;t fetch this post"}[failure]
            check(expected in await response.text())
    async with TestClient(TestServer(create_app(FakeExtractor(RuntimeError("network exploded")), BASE))) as client:
        response = await client.get(f"/api/{ID}")
        check(await response.json() == {"ok": False, "error": "error"})


async def proxy_and_grids():
    seen = {}
    pictures = [jpeg((20 + n, 10 + n), color) for n, color in enumerate(("red", "green", "blue", "yellow"))]

    async def cdn(request):
        seen[request.path] = request.headers.get("Range")
        if request.path == "/video.mp4":
            return web.Response(status=206, body=b"video", headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-4/5", "Accept-Ranges": "bytes"})
        return web.Response(body=pictures[int(request.match_info["number"])], content_type="image/jpeg")

    upstream = web.Application()
    upstream.router.add_get("/video.mp4", cdn)
    upstream.router.add_get("/{number}.jpg", cdn)
    server = TestServer(upstream)
    await server.start_server()
    try:
        video = result(video_url=str(server.make_url("/video.mp4")), thumbnail_url=str(server.make_url("/0.jpg")))
        async with TestClient(TestServer(create_app(FakeExtractor(video), BASE))) as client:
            response = await client.get(f"/video/{ID}", headers={"Range": "bytes=0-4"})
            check(response.status == 206 and await response.read() == b"video")
            check(response.headers["Content-Range"] == "bytes 0-4/5" and seen["/video.mp4"] == "bytes=0-4")
            response = await client.get(f"/image/{ID}/1")
            check(await response.read() == pictures[0])
        for count in (2, 3, 4):
            photos = result(video_url=None, has_video=False, thumbnail_url=str(server.make_url("/0.jpg")),
                            images=[str(server.make_url(f"/{n}.jpg")) for n in range(count)])
            async with TestClient(TestServer(create_app(FakeExtractor(photos), BASE))) as client:
                response = await client.get(f"/image/{ID}")
                with Image.open(BytesIO(await response.read())) as grid:
                    check(grid.size == (2048, 1024 if count == 2 else 2048))
    finally:
        await server.close()


async def run_tests():
    check(tweet_token("20") == "6dq1a2xwd93")
    check(tweet_token(ID) == "477tursh5n9")
    valid = [f"/SpaceX/status/{ID}", f"/SpaceX/status/{ID}/photo/3", f"/SpaceX/status/{ID}/video/1", f"/i/status/{ID}", f"/i/web/status/{ID}"]
    for path in valid:
        match = POST_RE.fullmatch(path)
        check(match is not None and (match.group(1) == "SpaceX" if "SpaceX" in path else True))
    check(POST_RE.fullmatch(f"/Space-X/status/{ID}") is None)
    check(all(marker in BOT_MARKERS for marker in ("discordbot", "slackbot", "bot")))
    await api_and_routes()
    await failures()
    await proxy_and_grids()
    for count in (2, 3, 4):
        grid, width, height = _make_grid([jpeg((10, 10), "red")] * count)
        check(bool(grid) and (width, height) == (2048, 1024 if count == 2 else 2048))


if __name__ == "__main__":
    run_page_checks()
    asyncio.run(run_tests())
    print(f"{TESTS} tests passed")
