# igembed

Makes Instagram links preview properly in Discord. Swap `instagram.com` for
`ig.milkhaus.net` in a post or reel link: Discord gets the video or photos to embed,
and a person who clicks it lands on Instagram. It's the sibling of
[xembed](../xembed/), which does the same for X.

**Runs on:** noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable at:** `ig.milkhaus.net`

## How it works

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) does the fetching. Videos embed as video.
  Photo posts and carousels embed as images, and a carousel becomes one grid of every
  photo (two columns up to four photos, three after that).
- Every post is tried logged out first. Only if that fails does it use `cookies.txt`, the
  session of a throwaway Instagram account I keep just for fetching (the "burner"). That
  keeps the burner's traffic low so Instagram leaves it alone.
- Routes: `GET /api/<id>` returns the post as JSON so a bot can post a carousel as
  separate images, and `/video/<id>`, `/image/<id>` and `/image/<id>/<n>` proxy the media.

Run it with `docker compose up -d --build`. To pick up a new yt-dlp, rebuild from
scratch with `docker compose build --pull --no-cache && docker compose up -d`. Tests
need no network: `python test_app.py` (with `aiohttp`, `yt-dlp` and `Pillow`
installed).

## If it breaks

My Discord bot (Teto) asks for a repair by dropping a request file, and a systemd path
watcher (`sudo ./install-heal.sh`) runs [`heal.sh`](heal.sh):

1. After a 3-minute cooldown it recreates the container if it's unhealthy and retries
   the post. A deleted post needs no fix.
2. A login or connection failure gets fresh cookies from the burner's session in the
   signed-in browser on noahlab ([virtual desktop](../../virtual-desktop/)), then a
   restart and another try.
3. If the burner got logged out, [`login_burner.py`](login_burner.py) logs it back in
   with Bitwarden's autofill shortcut, at most every 6 hours, without reading the password.
4. It leaves a result file for the bot. Anything it can't fix messages me.

## Files

| File | What it is |
|---|---|
| [`app.py`](app.py), [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) | The server |
| [`heal.sh`](heal.sh), [`install-heal.sh`](install-heal.sh), [`systemd/`](systemd/) | The repair path |
| [`export_cookies.py`](export_cookies.py), [`login_burner.py`](login_burner.py) | Cookie refresh and burner login |
| [`test_app.py`](test_app.py), [`test_page.py`](test_page.py), [`test_login_burner.py`](test_login_burner.py) | Tests |
| [`static/`](static/) | The landing page |
