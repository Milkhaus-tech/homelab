# igembed

A small, self-hosted Instagram embed fixer for Discord. Replace `instagram.com`
with `ig.milkhaus.net` in a reel or post URL; bots receive video OpenGraph tags,
while people are redirected to Instagram.

Photo posts and carousels embed as images (carousels use a stitched grid of the first four); `ignore_no_formats_error` lets yt-dlp remain the only extractor.

Run it with `docker compose up -d --build`. To update yt-dlp, rebuild from a fresh
base and package install:

```sh
docker compose build --pull --no-cache && docker compose up -d
```

If anonymous extraction becomes blocked, export Instagram cookies in Netscape
format as `cookies.txt`, then uncomment `IG_COOKIES_FILE` and the bind mount in
`docker-compose.yml`.

Caddy configuration:

```caddyfile
ig.milkhaus.net { reverse_proxy 10.0.0.2:8095 }
```

DNS is a Cloudflare A record for `ig` pointing to the VPS.

Run the network-free test suite with `python test_app.py` after installing
`aiohttp`, `yt-dlp`, and `Pillow`.
