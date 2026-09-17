# igembed

A small, self-hosted Instagram embed fixer for Discord. Replace `instagram.com`
with `ig.milkhaus.net` in a reel or post URL; bots receive video OpenGraph tags,
while people are redirected to Instagram.

Photo posts and carousels embed as images (carousels use a stitched grid of the first four); `ignore_no_formats_error` lets yt-dlp remain the only extractor.

Routes:

- `GET /api/<id>` returns post metadata and bot-friendly media URLs as JSON.
- `GET`/`HEAD /image/<id>/<n>` proxies one 1-based carousel image or a video's thumbnail.

A bot can use `/api/<id>` to post a photo carousel as individual images; Discord shows up to four images per embed group.

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

## Self-healing

The Discord bot requests a repair by atomically creating
`data/igembed.heal` in its repository with JSON fields `shortcode`, `reason`,
and `requested_at`. The host responds in `data/igembed.heal.result` with
`requested_at`, `healed`, `action` (`none`, `restart`, or `cookies`), `detail`,
and the Unix timestamp `finished_at`.

Install the root-owned path watcher with `sudo ./install-heal.sh`. On a request,
`heal.sh` removes the request immediately, observes a 180-second cooldown,
recreates an unhealthy container, and probes the reported post. An unavailable
post needs no repair. Authentication, extraction, or connectivity failures
trigger a cookie refresh followed by a restart and another probe. Every run
leaves an atomic result for the bot and records its steps in
`data/igembed-heal.log`.

Cookie refresh reads the burner account's session from Chrome on this host's
display `:0`, through its browser-level CDP endpoint on port 9222. It does not
open a tab. If that browser is gone or the burner is logged out, refresh fails,
the old cookie file is retained, and the reason appears in the healing log and
result.
