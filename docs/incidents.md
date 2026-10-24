# Things that broke

Stuff that went wrong and what I changed because of it. Each fix is somewhere in this
repo, linked at the end of each one. All of these happened on noahlab, back when it ran
everything by itself.

## A docker prune broke every game server

*Jul 2026 · noahlab*

For two weeks every game server on the panel failed to start with a missing network.
Wings (the Pterodactyl agent that runs the game containers) only creates its Docker
network when Wings itself starts. A routine `docker system prune -f` deleted that
network while Wings kept running, so nothing could start until Wings restarted.

What I changed: [`ptero-net-watchdog`](../services/pterodactyl/ptero-net-watchdog)
checks every 2 minutes and restarts Wings if the network is gone. I also don't run
`docker system prune` anymore. A lot of my images are local builds with nowhere to
re-pull them from, so I only prune images and build cache.

## The VPN restarted itself 579 times in a night

*Aug 2026 · noahlab*

Torrents kept dropping overnight. gluetun (the VPN container the torrent client lives
inside) had restarted its tunnel 579 times, 358 of them in one hour. Its health check
looked up hostnames through its own encrypted DNS, which stalls sometimes. A stalled
lookup failed the check, the failed check restarted the tunnel, the restart reset DNS,
and DNS stalled again.

What I changed: the health check hits IP addresses now (`1.1.1.1:443`, `8.8.8.8:443`)
and DNS goes out plain, so the check doesn't depend on DNS working. It's in
[`services/media/docker-compose.yml`](../services/media/docker-compose.yml).

## Jellyfin thumbnails starved the game servers

*Aug 2026 · noahlab*

A CS2 server I ran at the time kept lagging. Frames took 19–24 ms against a 15.6 ms
budget, but the logs showed the game itself was barely doing any work. It just wasn't
getting CPU time. Two fixes, each measured over five minutes:

1. **Pinning.** Games got their own cores and everything else got kept off them (games
   on 12–15 and media on 0–11 back then, 10–15 and 0–9 now). Long frames went from 22
   to 4 and load from 20.7 to 14.4.
2. **The actual cause.** Jellyfin's trickplay job (the hover-to-scrub thumbnails) was
   decoding every 10-bit HEVC file on the CPU at about 600%. Jellyfin ships with 10-bit
   hardware decoding off, so only 8-bit files used the GPU. Turning it on, plus
   transcode throttling, took load to 4.9 and long frames to 2.

I was sure the encoder was the problem. It was the decoder. Settings are in
[`services/jellyfin`](../services/jellyfin/).

## Too many browsers ran noahlab out of memory

*Aug 2026 · noahlab*

My fantasy football bot got its own desktop and browser for each league. Six idle
Chromiums plus everything else on noahlab used up the 32 GB, and the kernel's OOM
killer took out three of the browsers at once while the bot was using them.

What I changed: one desktop that's always up for the everyday stuff, and a second one
that only starts a few minutes before a live draft (a draft can't be redone) and shuts
down after. The browsers run with caps on renderer processes and memory. That's all in
[`virtual-desktop/`](../virtual-desktop/).

## The desktop stream had video but no input

*Aug 2026 · noahlab*

The first time I streamed the headless desktop to my phone, the picture was perfect and
nothing I tapped or typed did anything. Sunshine (the streaming server) was creating its
virtual keyboard, mouse and touch devices fine. Xorg logged `No input driver specified`
57 times and ignored every one, because the minimal install has no X input driver.

What I changed: installed `xserver-xorg-input-libinput`, and it stays installed. The
[input bridge](../virtual-desktop/bin/vd-input-bridge) also logs
`claim window closed with 0 device(s)` when a stream is going to be video-only. If
video works and input doesn't, check the X log before blaming the phone app.

## Queued torrents counted as hit-and-runs

*Aug 2026 · noahlab*

My private tracker started giving me hit-and-runs (strikes for not seeding long enough
after a download) even though I seed 24/7. qBittorrent was capped at 75 active
torrents, so 49 of them sat in the queue. A queued torrent stops checking in with the
tracker, and the tracker counts that as not seeding.

What I changed: downloads got capped at what the tracker allowed (3 at a time back
then) and seeding got no cap, so nothing sat in the queue. These days queueing is just
off. Cleanup moved into [`race-reaper.py`](../services/media/scripts/race-reaper.py), which only deletes a
torrent after it has seeded past the tracker's 10-day rule, and has its own tests.

## A locked resolv.conf broke Tailscale DNS

*Aug 2026 · noahlab*

Tailscale's MagicDNS (so names like `jesus` work over Tailscale) never worked on
noahlab. `/etc/resolv.conf` turned out to be a hand-written file locked with
`chattr +i`, and its first line was a bare `nameserver` with no address, which broke
tailscaled's DNS setup.

What I changed: put back the normal `systemd-resolved` symlink and let tailscaled push
`100.100.100.100` into resolved. If DNS ever acts weird, `lsattr /etc/resolv.conf` is
the first thing I check now.

## The backup skipped the files that mattered

*Aug 2026 · noahlab*

The nightly backup said it worked every night while skipping every file owned by root:
Home Assistant's logins, the MQTT password file, JWT secrets. Cron ran it as my user,
and `tar` treats "permission denied" as a warning.

What I changed: [`backup-stacks.sh`](../ops/backup-stacks.sh) runs as root now, and
real errors fail the run (tar exit code 2 or higher, a failed database dump, the mirror
drive missing). An hourly check messages me if the newest backup is too old.
