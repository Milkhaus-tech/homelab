# Ops

The scripts that keep the lab trustworthy: nightly backups to two disks, hourly
health checks that page a phone, and traffic dashboards for the game tunnel.

## Backups — [`backup-stacks.sh`](backup-stacks.sh)

Nightly at 04:30, **via `sudo` from cron** — run as the login user it silently
dropped every root-owned file (HA auth store, MQTT passwords, JWT secrets), which is
[incident #8](../docs/incidents.md#8-the-backup-that-silently-skipped-the-important-files).

- Tars every stack's config/state to a dated dir on the media pool; the Pterodactyl
  panel additionally gets a live `mysqldump` (credentials read inside the container,
  never on the host).
- Excludes only the regenerable (transcode temp, thumbnails, metadata caches) —
  trimming a run from ~8.7 G to ~2 G.
- 14-day retention, then the whole set is rsync-mirrored to `/mnt/backup` — a
  **separate physical disk**. A missing mirror mount is FATAL, never a silent skip.
- Error policy is explicit: `tar rc=1` (file changed mid-read) is expected on live
  databases; `rc≥2`, a failed dump, or a failed mirror fail the run.

## Alerting — [`homelab-alerts.sh`](homelab-alerts.sh)

Hourly self-check that ends in a phone push (via the
[`vd-flag`](../virtual-desktop/bin/vd-flag) → Home Assistant webhook path) when
something needs a human:

| Check | Fires when |
|---|---|
| disk | media pool ≥ 85 % |
| backup-age | newest backup > 26 h old (or none at all) |
| dead-containers | anything with an always/unless-stopped policy sits exited |
| mirror | the backup disk isn't mounted |

A state file re-arms each alert every 24 h so a persisting condition nags daily
instead of hourly; `--dry-run` prints every check and sends nothing. Known ceiling:
if dockerd itself dies, the container check reports nothing — the disk/backup checks
still fire.

## Cron map

| When | What |
|---|---|
| 04:30 daily | [`backup-stacks.sh`](backup-stacks.sh) (sudo) |
| :35 hourly | [`homelab-alerts.sh`](homelab-alerts.sh) |
| :20 hourly | [`race-reaper.py --apply`](../services/media/scripts/race-reaper.py) |
| 05:45 + 17:45 | [`livetv-curate.py`](../services/jellyfin/scripts/livetv-curate.py) |
| 05:15 Sunday | [`media-dedup.py --apply`](../services/media/scripts/media-dedup.py) |

(systemd timers handle the rest: Factorio updates daily, the Pterodactyl network
watchdog and PZ stats every 1–2 minutes, the war-room check every minute.)

## Update ritual

Backup first, then per stack: `docker compose pull && docker compose up -d`. Compose
edits do nothing until `up -d`; these services carry weeks of uptime, so changes are
batched and recreated deliberately. One trap worth repeating: **don't judge image
staleness by its `Created` date** — reproducible builds freeze it; ask the app its
version or compare digests.

## Traffic dashboards — [`portwatch.sh`](portwatch.sh) / [`portwatch-tally.sh`](portwatch-tally.sh)

Interactive tcpdump dashboards for the game tunnel (`wg0`): live per-port packet
lines, or a per-port tally redrawn once a second. The tally version reads tcpdump
through fd 3 rather than a pipe — a pipe would fork the counter loop into a subshell
and the dashboard would read zeros forever. Used to answer "is game traffic actually
arriving?" during the [three-firewall-layer](../docs/architecture.md#the-edge-path)
debugging.
