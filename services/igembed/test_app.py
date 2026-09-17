import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app import create_app


ID = "DdG5ctQhWco"
BASE = "https://example.test"


class FakeExtractor:
    def __init__(self, result):
        self.result = result

    def extract(self, shortcode):
        assert shortcode == ID
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


RESULT = {
    "video_url": "https://cdn.invalid/video.mp4",
    "thumbnail_url": "https://cdn.invalid/thumb.jpg",
    "width": 720,
    "height": 1280,
    "description": 'caption & "more"',
    "channel": "tester",
    "uploader_id": None,
    "uploader": "Test User",
    "like_count": 27781,
    "comment_count": 512,
}


async def run_tests():
    async with TestClient(TestServer(create_app(FakeExtractor(RESULT), BASE))) as client:
        response = await client.get(f"/reel/{ID}/", headers={"User-Agent": "Discordbot/2.0"})
        body = await response.text()
        assert response.status == 200
        assert f'<meta property="og:video" content="{BASE}/video/{ID}">' in body
        assert 'caption &amp; &quot;more&quot;' in body

        response = await client.get(f"/p/{ID}/?utm_source=test", allow_redirects=False)
        assert response.status == 302
        assert response.headers["Location"] == f"https://www.instagram.com/p/{ID}/?utm_source=test"

        for header in ({"Range": "bytes=0-100"}, {"Icy-MetaData": "1"}):
            response = await client.get(f"/reels/{ID}", headers=header, allow_redirects=False)
            assert response.status == 302
            assert response.headers["Location"] == f"/video/{ID}"

        assert (await client.get("/reel/no/", headers={"User-Agent": "Discordbot"})).status == 404
        assert (await client.get(f"/someone/tv/{ID}", headers={"User-Agent": "Discordbot"})).status == 200
        response = await client.get(f"/someone/reel/{ID}", headers={"User-Agent": "Slackbot"})
        assert response.status == 200

        response = await client.get("/oembed", params={"text": "❤️ 1", "url": "https://instagram.test/post"})
        assert await response.json() == {
            "author_name": "❤️ 1",
            "author_url": "https://instagram.test/post",
            "provider_name": "ig.milkhaus.net",
            "provider_url": "https://ig.milkhaus.net",
            "title": "Instagram",
            "type": "link",
            "version": "1.0",
        }

    async with TestClient(TestServer(create_app(FakeExtractor(RuntimeError("gone")), BASE))) as client:
        response = await client.get(f"/reel/{ID}", headers={"User-Agent": "Discordbot"})
        assert response.status == 200
        assert "couldn&#x27;t fetch this post" in await response.text()

    seen = {}

    async def cdn(request):
        seen["range"] = request.headers.get("Range")
        return web.Response(
            status=206,
            body=b"x" * 101,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": "bytes 0-100/1000",
                "Accept-Ranges": "bytes",
            },
        )

    cdn_app = web.Application()
    cdn_app.router.add_get("/video.mp4", cdn)
    cdn_server = TestServer(cdn_app)
    await cdn_server.start_server()
    proxy_result = dict(RESULT, video_url=str(cdn_server.make_url("/video.mp4")))
    try:
        async with TestClient(TestServer(create_app(FakeExtractor(proxy_result), BASE))) as client:
            response = await client.get(f"/video/{ID}", headers={"Range": "bytes=0-100"})
            assert response.status == 206
            assert response.headers["Content-Range"] == "bytes 0-100/1000"
            assert response.headers["Content-Type"] == "video/mp4"
            assert await response.read() == b"x" * 101
            assert seen["range"] == "bytes=0-100"
            response = await client.head(f"/video/{ID}", headers={"Range": "bytes=0-100"})
            assert response.status == 206
            assert response.headers["Content-Range"] == "bytes 0-100/1000"
            assert seen["range"] == "bytes=0-100"
    finally:
        await cdn_server.close()


if __name__ == "__main__":
    asyncio.run(run_tests())
    print("all tests passed")
