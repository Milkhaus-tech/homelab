# xembed

A small, self-hosted X/Twitter embed fixer for Discord. Replace `x.com` with
`x.milkhaus.net`; bots receive OpenGraph tags while people are redirected to X.

Routes:

- `GET /api/<id>` returns post metadata and bot-friendly media URLs as JSON.
- `GET`/`HEAD /video/<id>`, `/image/<id>`, and `/image/<id>/<n>` proxy media.
- X status URL shapes return an embed to bots and redirect human browsers.

Run it with `docker compose up -d --build`. To update yt-dlp, rebuild from a
fresh base and package install:

```sh
docker compose build --pull --no-cache && docker compose up -d
```

Caddy configuration:

```caddyfile
x.milkhaus.net { reverse_proxy 10.0.0.2:8099 }
```

DNS is a Cloudflare A record for `x` pointing to the VPS.

Run the network-free test suite with `python test_app.py` after installing
`aiohttp`, `yt-dlp`, and `Pillow`.
