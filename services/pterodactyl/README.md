# Pterodactyl game hosting

The game servers for my friends: Factorio, Project Zomboid and Minecraft.
[Pterodactyl](https://pterodactyl.io) is the web panel I run them from.

**Runs on:** the panel on jesus, a game server on each box ([the boxes](../../README.md#the-boxes)) · **Reachable at:** `panel.milkhaus.net`; game ports come in through the VPS ([how](../../docs/architecture.md#game-servers))

## How it works

- **The panel** is this compose file (panel + MariaDB + Redis) on jesus, port 8081,
  behind Caddy. Its real secrets live in a panel-managed `var/.env` that never gets
  committed. My theme is three files mounted over the stock ones.
- **Wings**, Pterodactyl's agent, runs natively on all three boxes and starts each game
  in its own container. The panel reaches each one through Caddy at `node1.`, `jesus.`
  and `pablo.milkhaus.net`.
- **Factorio** is on noahlab, **Zomboid** on jesus, **Minecraft** on pablo. Factorio
  and Zomboid get their own cores ([how](../../docs/architecture.md#keeping-games-smooth)).

## Factorio updates

Factorio won't let you join a server on a different version, so
[`factorio-autoupdate`](factorio-autoupdate) checks factorio.com every day at 06:00.
When there's a new stable release it stops the server with `/quit` so the world saves,
snapshots `saves/` with hard links, reinstalls, and only deletes the snapshot once the
new version is hosting. Every step gets checked against the server's real state,
because Wings answers "queued", not "done". It messages me if anything fails, and never
starts a server I stopped myself.

## Minecraft versions

- Paper's newest builds need **Java 25**. The default Java 21 image dies with a
  one-line error, so the server uses the Java 25 image.
- The plugins (EssentialsX, CoreProtect, GriefPrevention and friends) lag behind new
  Minecraft releases, so the version is pinned to the newest one they all support.
- The whitelist is managed from Discord by my bot, which checks names against Mojang
  first. RCON is never forwarded from the VPS.

## Worth knowing

- Wings only creates its Docker network when it starts, so a `docker system prune` can
  break every server. [`ptero-net-watchdog`](ptero-net-watchdog) restarts Wings when the
  network is missing. It's only on noahlab so far
  ([what happened](../../docs/incidents.md#a-docker-prune-broke-every-game-server)).
- A 502 in the panel logs usually means the WireGuard tunnel is down, not Wings.
- Backups: the panel keeps three per server on each box, and the nightly
  [backup](../../ops/) copies the panel database and every world to noahlab.

## Files

| File | What it is |
|---|---|
| [`docker-compose.yml`](docker-compose.yml), [`.env.example`](.env.example) | The panel, MariaDB and Redis |
| [`factorio-autoupdate`](factorio-autoupdate), [`systemd/factorio-autoupdate.*`](systemd/) | The daily Factorio updater and its timer |
| [`ptero-net-watchdog`](ptero-net-watchdog), [`systemd/ptero-net-watchdog.*`](systemd/) | Puts the Wings network back, every 2 minutes |
