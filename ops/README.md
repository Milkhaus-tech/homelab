# Ops

Nightly backups for the whole lab, an hourly health check that messages me, and two
little traffic monitors for the game tunnel.

**Runs on:** noahlab, from cron ([the boxes](../README.md#the-boxes))

## Backups

[`backup-stacks.sh`](backup-stacks.sh) runs every night at 04:30 as root:

- **noahlab:** every stack's config and data, minus stuff that rebuilds itself
  (transcode temp, thumbnails, metadata caches).
- **jesus:** a dump of the game panel's database, plus the panel, Frigate, Grafana and
  Prometheus configs, my bots, and the Zomboid world.
- **pablo:** the Minecraft world, after telling the server to flush and pause saving.
- **VPS:** the Caddy, WireGuard and firewall config.

That's about 6.5 GB a night into `/mnt/media/backups/<date>/`, kept 14 days and mirrored
to `/mnt/backup` on a separate drive. A `tar` exit code of 1 (a file changed mid-read) is
normal on live databases. Exit code 2 or more, a failed dump, or a missing mirror drive
fails the run and sends me a Telegram message. It runs as root because as my user it
skipped every root-owned file
([what happened](../docs/incidents.md#the-backup-skipped-the-files-that-mattered)).

## Health check

[`homelab-alerts.sh`](homelab-alerts.sh) runs hourly and messages me through
[`vd-flag`](../virtual-desktop/bin/vd-flag) when something on noahlab needs a person:

| Check | Fires when |
|---|---|
| disk | the media drive is 85% full or more. Alerts when it crosses 85, 90 or 95%, then weekly (daily at 95%+) |
| backup-age | the newest backup is more than 26 hours old, or there isn't one |
| dead-containers | a container set to restart `always` or `unless-stopped` is stopped |
| mirror | the backup drive isn't mounted |

The other alerts repeat daily while the problem lasts. `--dry-run` prints every check
and sends nothing.

## Cron on noahlab

| When | What |
|---|---|
| 04:30 daily | [`backup-stacks.sh`](backup-stacks.sh) |
| :35 hourly | [`homelab-alerts.sh`](homelab-alerts.sh) |
| :20 hourly | [`race-reaper.py --apply`](../services/media/scripts/race-reaper.py) |
| 05:45 + 17:45 | [`livetv-curate.py`](../services/jellyfin/scripts/livetv-curate.py) |
| 05:15 Sunday | [`media-dedup.py --apply`](../services/media/scripts/media-dedup.py) |

A few more jobs and timers aren't published here. The ones that are (Factorio updater,
Wings network watchdog, Zomboid stats page) sit next to their services.

## Worth knowing

- Update with a backup first, then `docker compose pull && docker compose up -d` per
  stack. Editing a compose file does nothing until `up -d`.
- Check whether an image is out of date by asking the app its version or comparing
  digests. The image's `Created` date is often frozen by reproducible builds.
- `portwatch-tally.sh` reads tcpdump through file descriptor 3 instead of a pipe. A pipe
  would put the counter in a subshell and the screen would show zeros forever.

## Files

| File | What it is |
|---|---|
| [`backup-stacks.sh`](backup-stacks.sh) | Nightly backup of every box, as root |
| [`homelab-alerts.sh`](homelab-alerts.sh) | Hourly health check |
| [`portwatch.sh`](portwatch.sh), [`portwatch-tally.sh`](portwatch-tally.sh) | Live and per-port game traffic on `wg0` |
