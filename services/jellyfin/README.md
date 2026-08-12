# Jellyfin

Streaming front-end for the media pipeline: GPU-transcoded, plugin-extended, with a
curated free live-TV lineup rebuilt twice a day.

## Version pinning

The image is pinned (`jellyfin/jellyfin:10.11.11`), not `:latest`, because the
File-Transformation plugin family is **ABI-pinned per Jellyfin patch version**: each
release ships `Release-<version>.zip` builds, and the highest *version number* is often
a different-ABI build that loads cleanly and then silently does nothing. A server bump
means re-fetching the matching `Release-<newver>.zip` for every plugin in that family.

| Plugin | Role |
|---|---|
| Media Bar | Home-screen hero carousel |
| Home Screen Sections | Modern sectioned home (trimmed to 18 movie/show/request sections) |
| File Transformation | Shared patching framework the two above depend on |
| Trickplay | Hover-scrub previews, generated on the GPU |

Plugins here patch the **web client only** — phone/TV apps render their stock UI. After
plugin changes, hard-reload the browser: the injections live in `index.html` plus a
hard-cached home chunk.

## Encoding

NVENC/NVDEC on the GTX 1660 SUPER, with the session limit lifted by the public
`nvidia-patch`. Two non-default switches matter
([incident #3](../../docs/incidents.md#3-jellyfin-trickplay-starves-the-game-servers)):

- **10-bit HEVC/VP9 NVDEC enabled** — off by default, which silently software-decodes
  every `yuv420p10le` file at ~600 % CPU while 8-bit uses the GPU. Turing decodes
  HEVC Main10 fine; the RExt flags stay off (Turing cannot).
- **Transcode throttling enabled** — playback transcodes pause once the client is
  buffered ahead, instead of racing to encode the whole file.

Edit `encoding.xml` only with the container stopped; Jellyfin rewrites it on shutdown.

## Live TV — 84 curated channels

[`scripts/livetv-curate.py`](scripts/livetv-curate.py) (cron 05:45 + 17:45) builds the
tuner inputs from free, legal FAST feeds:

- Playlists from the BuddyChewChew generator (Pluto / Samsung TV Plus / Roku US);
  EPGs from i.mjh.nz. (The i.mjh.nz *playlists* are dead — only its EPGs work.)
- Filters ~1,500 upstream channels down to a hand-picked `LINEUP`, renumbered by
  bucket: 100s sports, 200s news, 300s entertainment, 400s anime, 500s music.
- Writes `curated.m3u` + a merged, filtered `guide.xml` atomically, refuses to
  overwrite on a zero-programme fetch, then triggers a Jellyfin guide refresh via API.
- Lineup misses are logged, not fatal; `--selftest` covers the parse/filter/renumber
  logic offline.

Guide upstreams only carry ~17–36 h of data, so the twice-daily cadence is
load-bearing — don't reduce it. DVR records to the media pool.

## Invites

Accounts are invite-only via **jfa-go** (defined in the [media stack](../media/)),
which manages invite links and password resets against Jellyfin's user database.

## Theming

The web client carries a custom skin (accent overrides, login theme, custom loading
spinner) injected through Jellyfin's branding API (`CustomCss` + `LoginDisclaimer`) —
configuration state, not repo files; the art assets aren't redistributed here.
