# pzstats

A public live-stats page for the Project Zomboid server: who's on now, hours survived,
real-world playtime, skills, and world size — nginx serving a static page plus a
`stats.json` regenerated every minute by a systemd timer.

[`generate.py`](generate.py) merges three sources:

- **A2S query** against the game port — is the server up, who is on right now
  (Zomboid answers Source queries on its *game* port, not the second UDP port).
- **PerkLog** — per-character hours survived and skill levels.
- **join/leave logs** — paired into sessions for real-world playtime; an unmatched
  join still counts up to the last event seen, so a crash never silently shortens
  someone's number.

Logs older than the current world's epoch are ignored — they describe a map that no
longer exists. The page deliberately publishes **no Steam IDs and no chat contents**;
it's reachable by anyone with the URL. Output is written atomically so the web server
never reads a half-written file.

The page art isn't redistributed in this repo (`www/` ships the HTML only).
