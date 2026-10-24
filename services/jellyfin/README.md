# Jellyfin

The movie and TV site my friends and I watch on. [Jellyfin](https://jellyfin.org) is a
self-hosted streaming server; this one transcodes on the GPU and has free live TV.

**Runs on:** noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable at:** `stream.milkhaus.net`, through a Cloudflare tunnel ([why](../../docs/architecture.md#how-traffic-gets-in)) · **Talks to:** the [media pipeline](../media/)

## How it works

- **Version pinned** to `jellyfin/jellyfin:10.11.11`, not `:latest`. The home-screen
  plugins (Media Bar, Home Screen Sections, and File Transformation, which they both
  depend on) are built separately for each Jellyfin version. A build for the wrong
  version can load fine and then do nothing. So a Jellyfin update also means grabbing
  the matching `Release-<version>.zip` of each of those plugins.
- **GPU transcoding** (NVENC/NVDEC on the GTX 1660 SUPER), with the session limit lifted
  by the public [`nvidia-patch`](https://github.com/keylase/nvidia-patch). Two settings
  that are off by default matter a lot:
  - **10-bit HEVC/VP9 hardware decoding.** Without it every 10-bit file gets decoded on
    the CPU at about 600%
    ([what happened](../../docs/incidents.md#jellyfin-thumbnails-starved-the-game-servers)).
  - **Transcode throttling.** A transcode pauses once the player has enough buffered,
    instead of racing through the whole file.
- **Live TV.** [`scripts/livetv-curate.py`](scripts/livetv-curate.py) builds an
  84-channel lineup out of free ad-supported channels (Pluto, Samsung TV Plus, Roku),
  using [BuddyChewChew's playlists](https://github.com/BuddyChewChew/app-m3u-generator)
  and [i.mjh.nz](https://i.mjh.nz) guides. It picks mine out of about 1,500, numbers them
  by type (100s sports, 200s news, and so on) and tells Jellyfin to refresh.
- **Invites** go through jfa-go at `join.milkhaus.net`, which lives in the
  [media stack](../media/). Accounts are invite-only.

## Worth knowing

- The live TV script runs at 05:45 and 17:45. The guide sources only carry 17–36 hours
  of listings, so running it less often leaves gaps in the guide.
- The script never overwrites a working guide with an empty one. `--selftest` tests it
  offline.
- Edit `encoding.xml` only while Jellyfin is stopped. It rewrites the file on shutdown.
- The web plugins only change the browser version. Phone and TV apps look stock. After
  changing plugins, hard-reload the browser.

## Files

| File | What it is |
|---|---|
| [`docker-compose.yml`](docker-compose.yml) | Jellyfin (pinned, GPU, kept off the game cores) and the Cloudflare tunnel |
| [`scripts/livetv-curate.py`](scripts/livetv-curate.py) | Builds the live TV lineup and guide |
