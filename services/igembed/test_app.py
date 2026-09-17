import asyncio
from io import BytesIO

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

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

PHOTO_RESULT = {
    "video_url": None,
    "thumbnail_url": "https://cdn.invalid/photo.jpg",
    "images": ["https://cdn.invalid/photo.jpg"],
    "width": None,
    "height": None,
    "description": "photo caption",
    "channel": "photographer",
    "uploader_id": None,
    "uploader": None,
    "like_count": 12,
    "comment_count": 3,
}


def jpeg(size, color):
    output = BytesIO()
    Image.new("RGB", size, color).save(output, "JPEG")
    return output.getvalue()


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

    failures = (
        ("please LOGIN to view this private post", "auth", "Instagram won&#x27;t show this post without a login"),
        ("cookies are required", "auth", "Instagram won&#x27;t show this post without a login"),
        ("empty media response", "auth", "Instagram won&#x27;t show this post without a login"),
        ("site is not granting access", "auth", "Instagram won&#x27;t show this post without a login"),
        ("rate-limit reached", "auth", "Instagram won&#x27;t show this post without a login"),
        ("post not found", "gone", "this post is unavailable"),
        ("post does not exist", "gone", "this post is unavailable"),
        ("post unavailable", "gone", "this post is unavailable"),
        ("post was removed", "gone", "this post is unavailable"),
        ("this post is private", "gone", "this post is unavailable"),
        ("unexpected extractor failure", "error", "couldn&#x27;t fetch this post"),
    )
    for message, classification, description in failures:
        async with TestClient(TestServer(
            create_app(FakeExtractor(RuntimeError(message)), BASE)
        )) as client:
            response = await client.get(f"/reel/{ID}", headers={"User-Agent": "Discordbot"})
            assert response.status == 200
            assert response.headers["X-Igembed-Error"] == classification
            assert description in await response.text()
            for path in (f"/video/{ID}", f"/image/{ID}"):
                response = await client.get(path)
                assert response.status == 502
                assert response.headers["X-Igembed-Error"] == classification

    async with TestClient(TestServer(create_app(FakeExtractor(PHOTO_RESULT), BASE))) as client:
        response = await client.get(f"/p/{ID}/", headers={"User-Agent": "Discordbot/2.0"})
        body = await response.text()
        assert response.status == 200
        assert f'<meta property="og:image" content="{BASE}/image/{ID}">' in body
        assert '<meta name="twitter:card" content="summary_large_image">' in body
        assert 'property="og:type" content="website"' in body
        assert "og:video" not in body
        response = await client.get(
            f"/p/{ID}/", headers={"Range": "bytes=0-100"}, allow_redirects=False,
        )
        assert response.status == 302
        assert response.headers["Location"] == f"/image/{ID}"

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

    image_hits = []
    image_data = [
        jpeg((20, 10), "red"), jpeg((10, 20), "green"), jpeg((30, 30), "blue"),
    ]

    async def image_cdn(request):
        index = int(request.match_info["index"])
        image_hits.append(index)
        return web.Response(body=image_data[index], content_type="image/jpeg")

    image_app = web.Application()
    image_app.router.add_get("/{index}.jpg", image_cdn)
    image_server = TestServer(image_app)
    await image_server.start_server()
    try:
        urls = [str(image_server.make_url(f"/{index}.jpg")) for index in range(3)]
        grid_result = dict(PHOTO_RESULT, thumbnail_url=urls[0], images=urls)
        async with TestClient(TestServer(create_app(FakeExtractor(grid_result), BASE))) as client:
            response = await client.get(f"/image/{ID}")
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/jpeg"
            with Image.open(BytesIO(await response.read())) as grid:
                assert grid.size == (2048, 2048)
            assert sorted(image_hits) == [0, 1, 2]
            response = await client.get(f"/image/{ID}")
            assert response.status == 200
            assert sorted(image_hits) == [0, 1, 2]
            response = await client.get(f"/p/{ID}/", headers={"User-Agent": "Discordbot"})
            body = await response.text()
            assert "photo caption (3 photos)" in body
            assert '<meta property="og:image:width" content="2048">' in body
            assert '<meta property="og:image:height" content="2048">' in body
    finally:
        await image_server.close()

    fallback_hits = []

    async def failing_cdn(request):
        index = int(request.match_info["index"])
        fallback_hits.append(index)
        if index == 1:
            return web.Response(status=500)
        return web.Response(body=image_data[index], content_type="image/jpeg")

    fallback_app = web.Application()
    fallback_app.router.add_get("/{index}.jpg", failing_cdn)
    fallback_server = TestServer(fallback_app)
    await fallback_server.start_server()
    try:
        urls = [str(fallback_server.make_url(f"/{index}.jpg")) for index in range(3)]
        fallback_result = dict(PHOTO_RESULT, thumbnail_url=urls[0], images=urls)
        async with TestClient(TestServer(create_app(FakeExtractor(fallback_result), BASE))) as client:
            response = await client.get(f"/image/{ID}")
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/jpeg"
            assert await response.read() == image_data[0]
            assert fallback_hits.count(0) == 2
    finally:
        await fallback_server.close()


if __name__ == "__main__":
    asyncio.run(run_tests())
    print("all tests passed")
