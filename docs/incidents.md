# Incidents & lessons

Short post-mortems of the outages that shaped this lab's design. Each fix lives in
config or code somewhere in this repo; these are the reasons why.

---

## 1. `docker system prune` deletes a game network

**Jul 2026.** Every Pterodactyl server start failed for two weeks with a missing
network. Root cause: Wings creates its docker network (`pterodactyl_nw`) **only at its
own startup**; a routine `docker system prune -f` deleted it (and a stopped game
container) while Wings kept running.

**Fix:** [`ptero-net-watchdog`](../services/pterodactyl/ptero-net-watchdog) — a
five-line oneshot on a 2-minute timer that restarts Wings when the network is missing.
Prunes are scoped now (`docker image prune`, `docker builder prune`), and bare
`docker system prune` is banned on this box: six images are local builds with no
registry to re-pull from.

**Lesson:** self-heal the class of failure, not the instance; the watchdog costs
nothing and has already caught recurrences.

## 2. The VPN restart loop (579 restarts in one night)

**Aug 2026.** Torrent connections died repeatedly overnight — 579 tunnel resets in one
night, 358 in a single hour. gluetun's health check resolves DNS names through its
own DNS-over-TLS resolver, which periodically stalls; a stalled resolver fails the
health check, which restarts the tunnel, which resets the resolver, which stalls…

**Fix:** health targets pinned to IP literals (`HEALTH_TARGET_ADDRESSES=1.1.1.1:443,8.8.8.8:443`)
and plain DNS upstream — the health path no longer depends on the thing it's
implicitly testing. See [`services/media/docker-compose.yml`](../services/media/docker-compose.yml).

**Lesson:** a health check that shares a failure domain with the system under test
turns one flaky component into a self-reinforcing outage.

## 3. Jellyfin Trickplay starves the game servers

**Aug 2026.** CS2 frames ran 19–24 ms against a 15.6 ms tick budget — but the log
signature (`UNEXPECTED LONG FRAME` with large elapsed and ~0.1 ms sim time) showed
scheduling delay, not server load. The box was busy; the game just wasn't getting
scheduled.

Two-stage fix, both measured:

1. **CPU pinning** (games `12-15`, media `0-11`): long frames 22 → 4 per 5 min,
   load 20.7 → 14.4.
2. **Root cause:** Trickplay thumbnail jobs were software-decoding every **10-bit**
   HEVC file at ~600 % CPU — `EnableDecodingColorDepth10Hevc` defaulted off, so NVDEC
   handled 8-bit while `yuv420p10le` fell back to CPU. Enabling 10-bit HEVC/VP9 NVDEC
   plus transcode throttling: load 14.4 → 4.9, long frames 4 → 2.

**Lesson:** "the transcoder is eating the CPU" was the obvious theory and the wrong
one — the encoder was fine, the *decoder* fell back. Verify which half of the pipeline
runs on silicon before buying a GPU.

## 4. Six idle Chromiums invoke the OOM killer

**Aug 2026.** The first virtual-desktop design gave each fantasy league its own
desktop + browser. Six idle Chromiums plus the container stack pushed the 32 GB box
into the OOM killer, which took three browsers out from under their agents at once.

**Fix:** the [two-desktop architecture](../virtual-desktop/) — one always-on
*standard* desktop shared by all leagues, and a dormant *war room* woken five minutes
before a real draft (the one event that can't be redone), torn down after. Browsers
run lean: 2-renderer limit, capped JS heap, background networking off.

**Lesson:** browsers are the heaviest thing on the box; provision them like workloads,
not tabs. Rare events get dedicated resources *only while they exist*.

## 5. The video-only stream (missing input driver)

**Aug 2026.** First Moonlight connection to the headless desktop: perfect video, zero
input. Sunshine was creating its virtual keyboard/mouse/touch devices correctly —
Xorg logged `No input driver specified` 57 times and ignored every one, because the
minimal headless package set includes no X input driver at all.

**Fix:** `xserver-xorg-input-libinput` must stay installed. The virtual-desktop docs
call it out as load-bearing, and the input bridge logs a
`claim window closed with 0 device(s)` warning when a stream would be video-only.

**Lesson:** a stream with video but no input is an *input-stack* problem, not a
Moonlight problem; check the X log before the client.

## 6. Queue policy quietly generates tracker hit-and-runs

**Aug 2026.** The private-tracker account started accruing hit-and-runs despite
seeding 24/7. qBittorrent's old 75-active-torrent cap had parked 49 torrents in
`queuedUP` — and a queued torrent **stops announcing**, which the tracker counts as
not seeding.

**Fix:** the queue caps what the tracker actually limits — 3 active *downloads*
(the tracker grants exactly 3 slots), unlimited seeds/announces. Reclamation moved
into [`race-reaper.py`](../services/media/scripts/race-reaper.py), which only deletes
races that are past the tracker's 10-day hit-and-run window *and* dead, with a disk
ceiling that never violates the window.

**Lesson:** client-side resource policy is tracker-visible behavior. Model the
tracker's rules in code (with self-tests), not in slider settings.

## 7. The immutable resolv.conf

**Aug 2026.** Tailscale MagicDNS never worked on this box. `/etc/resolv.conf` turned
out to be a hand-written file pinned with `chattr +i` — with a malformed bare
`nameserver` first line that broke tailscaled's DNS integration entirely.

**Fix:** restore the `systemd-resolved` stub symlink and let tailscaled push
`100.100.100.100` into resolved. If DNS misbehaves here, `lsattr /etc/resolv.conf`
is the first diagnostic, not the last.

**Lesson:** immutable flags outlive the reason they were set. Leave a dated backup and
a note, or future-you will fight a file that can't be edited and won't say why.

## 8. The backup that silently skipped the important files

**Aug 2026.** Nightly backups ran green while silently dropping every root-owned file —
Home Assistant's auth store, the MQTT password file, JWT secrets — because the cron
job ran as the login user and `tar` treated permission errors as warnings.

**Fix:** the backup runs under `sudo` from cron, treats `tar rc≥2` / failed `mysqldump`
/ missing mirror mount as FATAL, and the hourly [alerter](../ops/homelab-alerts.sh)
pushes to a phone when the newest backup is stale. Recoverability is checked, not
assumed.

**Lesson:** a backup job's exit code is a claim about *completeness*, not just
"tar ran". Decide explicitly which errors are fatal.
