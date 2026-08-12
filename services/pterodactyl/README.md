# Pterodactyl game hosting

Panel + native Wings hosting three dedicated servers — Project Zomboid, Factorio
(Space Age), and Minecraft (Paper) — behind the [edge VPS](../../edge/), with
self-healing infrastructure and unattended version management.

## Moving parts

| Part | Where | Notes |
|---|---|---|
| Panel | compose here (`panel` + MariaDB + Redis), host `:8081` | fronted by `panel.milkhaus.net` at the edge; real secrets live in panel-managed `var/.env` (git-excluded) |
| Wings | native binary, `wings.service` | game containers on its own docker network; config in `/etc/pterodactyl/` (holds the node token — never committed) |
| Game servers | Wings-managed containers | pinned to CPU cores 12–15 (see [architecture](../../docs/architecture.md#compute-isolation)) |
| Theme | `themes/` blade + css overlays, bind-mounted read-only | a pure overlay, no fork: revert = remove three mounts |

## Self-healing: the network watchdog

Wings creates its docker network **only at its own startup**; a stray
`docker system prune` once deleted it and broke every server start for two weeks
([incident #1](../../docs/incidents.md#1-docker-system-prune-deletes-a-game-network)).
[`ptero-net-watchdog`](ptero-net-watchdog) + a 2-minute
[timer](systemd/ptero-net-watchdog.timer) restarts Wings whenever the network is
missing — recovery in ≤2 minutes instead of a two-week mystery.

## Unattended Factorio updates

Cross-version multiplayer is impossible in Factorio: an outdated server is an
unjoinable one. [`factorio-autoupdate`](factorio-autoupdate) (daily
[timer](systemd/factorio-autoupdate.timer)) keeps the server on current stable:

1. Compares the installed `data/base/info.json` against factorio.com's stable release
   (a failed fetch keeps the working server and retries tomorrow).
2. Stops via the egg's `/quit` so the world **saves** — never lets the reinstall's
   grace period SIGKILL a save in progress.
3. Hard-link snapshots `saves/` (zero space) before reinstalling; the snapshot is only
   removed after the new build is confirmed *hosting*.
4. Verifies each async Wings action against actual state — a 202 means "queued", not
   "done" — and pushes a phone alert on any failure.

It only updates; it never starts a server an admin deliberately stopped.

## Minecraft (Paper) — version traps

Two pins that look arbitrary and aren't:

- Paper `latest` resolved to a Minecraft version requiring **Java 25**; the egg
  default (Java 21) dies with a one-line error. The image is pinned to the Java 25
  yolk.
- The QOL plugin ecosystem (EssentialsX, CoreProtect, GriefPrevention) had **no
  compatible builds** for the newest MC — `MINECRAFT_VERSION` is pinned to the newest
  release where the whole plugin set works. Check compatibility before bumping;
  `latest` strands the plugins again.

RCON is LAN-only (deliberately never DNAT'd); the whitelist is driven from Discord by
a bot cog that validates names against Mojang before adding. One plugin is banned
after testing: a world-pregen plugin that reliably hung the server into a
kill-only state despite claiming compatibility.

## Network path

Game UDP/TCP arrives via VPS DNAT over WireGuard — never through the HTTP proxy. Port
onboarding needs **three** firewall layers (provider cloud firewall → ufw → DNAT) and
game subdomains must be grey-cloud DNS-only records; the full story is in
[docs/architecture.md](../../docs/architecture.md#the-edge-path). Panel↔Wings traffic
hairpins through the edge (`behind_proxy`), so 502s in panel logs usually mean tunnel
trouble, not a Wings bug.

## Backups

Nightly [`backup-stacks.sh`](../../ops/backup-stacks.sh) dumps the panel database
(`mysqldump` inside the container, credentials never leave it) and tars panel + wings
config; world saves ride the panel's own scheduled backups. A live stats page for the
Zomboid server is generated separately — see [`services/pzstats`](../pzstats/).
