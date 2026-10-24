# pzstats

A public live-stats page for my Project Zomboid server: who's on now, hours survived,
real-world playtime, skills, and world size. It's nginx serving a static page plus a
`stats.json` that a systemd timer rebuilds every minute.

**Runs on:** noahlab, reading the game server's logs from jesus over NFS ([the boxes](../../README.md#the-boxes)) · **Reachable at:** [pz.milkhaus.net](https://pz.milkhaus.net)

## How it works

[`generate.py`](generate.py) merges three sources:

- **An A2S query** (the Steam server query) against the game port: is the server up, and
  who's on right now. Zomboid answers it on the *game* port, not the second UDP port.
- **PerkLog:** hours survived and skill levels for each character.
- **Join and leave logs,** paired into sessions for real-world playtime. A join with no
  matching leave still counts up to the last event seen, so a crash doesn't shorten
  anyone's number.

## Worth knowing

- Logs from before the current world started are ignored, since they describe a map
  that's gone.
- The page shows no Steam IDs and no chat, because anyone with the link can see it.
- Output is written atomically, so nginx never serves a half-written file.
- The page art isn't in this repo; `www/` only has the HTML.

## Files

| File | What it is |
|---|---|
| [`generate.py`](generate.py) | Builds `stats.json` from the query and the logs |
| [`www/index.html`](www/index.html) | The page |
| [`docker-compose.yml`](docker-compose.yml) | nginx on port 8089, kept off the game cores |
| [`systemd/`](systemd/) | The every-minute timer |
