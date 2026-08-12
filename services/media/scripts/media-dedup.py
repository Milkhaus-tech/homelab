#!/usr/bin/env python3
"""Guardrail against duplicate library versions on /mnt/media.

Keeps exactly one video file per movie / per episode. Rules (from Noah):
  - 720p preferred, 1080p acceptable — never re-grab to "improve" resolution.
  - NEVER remove a file that is being seeded (shares an inode with /mnt/media/downloads).
  - NEVER hard-delete — move to a dated quarantine with a restore manifest; purge after 14 days.
  - Radarr/Sonarr-aware: the arr-tracked file is always the keeper, so nothing re-downloads.

Dry-run by default. Pass --apply to actually move files. Weekly cron uses --apply.
Today this finds 0 duplicates; it exists to catch future ones (manual imports, failed upgrades).
"""
import argparse, json, os, shutil, sys, time, urllib.request
from datetime import date

MOVIES = "/mnt/media/movies"
SHOWS = "/mnt/media/shows"
DOWNLOADS = "/mnt/media/downloads"
TRASH = "/mnt/media/.dedup-trash"
ENV = "/home/noah/docker/qbittorrentvpn/.env"
VIDEO = {".mkv", ".mp4", ".avi", ".m4v", ".ts", ".wmv", ".mov"}
EXTRA_DIRS = {"featurettes", "extras", "behind the scenes", "deleted scenes", "samples", "other", "trailers"}
RETAIN_DAYS = 14
# Lower rank = more preferred to KEEP. 720p wins; 1080p fine; 4K deprioritised (big); tiny last.
RES_RANK = {"720p": 0, "1080p": 1, "576p": 2, "480p": 3, "2160p": 4, "unknown": 5}
import re
RES_RE = re.compile(r"(2160p|1080p|720p|576p|480p)", re.I)
EP_RE = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")


def res_of(name):
    m = RES_RE.search(name)
    return m.group(1).lower() if m else "unknown"


def load_env():
    return dict(l.strip().split("=", 1) for l in open(ENV) if "=" in l and not l.startswith("#"))


def arr_tracked_paths(env):
    """Absolute host paths of every file Radarr/Sonarr currently tracks (the keepers)."""
    tracked = set()

    def call(base, key, path):
        req = urllib.request.Request(base + path, headers={"X-Api-Key": key})
        return json.load(urllib.request.urlopen(req, timeout=30))

    def host(p):  # container /media/... -> host /mnt/media/...
        return p.replace("/media/", "/mnt/media/", 1) if p and p.startswith("/media/") else p

    try:
        for m in call("http://localhost:7878", env["RADARR_API_KEY"], "/api/v3/movie"):
            mf = m.get("movieFile")
            if mf and mf.get("path"):
                tracked.add(host(mf["path"]))
    except Exception as e:
        print(f"  WARN: radarr unreachable ({e}); movies fall back to resolution-preference keeper", file=sys.stderr)
    try:
        for s in call("http://localhost:8989", env["SONARR_API_KEY"], "/api/v3/series"):
            for ef in call("http://localhost:8989", env["SONARR_API_KEY"], f"/api/v3/episodefile?seriesId={s['id']}"):
                if ef.get("path"):
                    tracked.add(host(ef["path"]))
    except Exception as e:
        print(f"  WARN: sonarr unreachable ({e}); episodes fall back to resolution-preference keeper", file=sys.stderr)
    return tracked


def seeded_inodes():
    """(dev, inode) of every downloads file with >1 link — i.e. hardlinked into the library = seeding."""
    s = set()
    for root, dirs, files in os.walk(DOWNLOADS):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            if st.st_nlink > 1:
                s.add((st.st_dev, st.st_ino))
    return s


def video_files(folder):
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d.lower() not in EXTRA_DIRS]
        for f in files:
            if os.path.splitext(f)[1].lower() in VIDEO and "sample" not in f.lower() and "-trailer" not in f.lower():
                fp = os.path.join(root, f)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                out.append({"path": fp, "size": st.st_size, "res": res_of(f),
                            "key": (st.st_dev, st.st_ino)})
    return out


def groups():
    """Yield (label, [file,...]) for each movie folder and each episode (series + SxxEyy)."""
    if os.path.isdir(MOVIES):
        for d in sorted(os.listdir(MOVIES)):
            p = os.path.join(MOVIES, d)
            if os.path.isdir(p):
                vids = video_files(p)
                if len(vids) > 1:
                    yield f"movie:{d}", vids
    if os.path.isdir(SHOWS):
        for series in sorted(os.listdir(SHOWS)):
            sp = os.path.join(SHOWS, series)
            if not os.path.isdir(sp):
                continue
            eps = {}
            for v in video_files(sp):
                m = EP_RE.search(os.path.basename(v["path"]))
                if m:
                    eps.setdefault((int(m.group(1)), int(m.group(2))), []).append(v)
            for (s, e), lst in eps.items():
                if len(lst) > 1:
                    yield f"show:{series} S{s:02}E{e:02}", lst


def pick_keeper(files, tracked):
    on_disk = [f for f in files if f["path"] in tracked]
    if on_disk:  # arr-tracked file is the keeper (prevents re-download)
        return min(on_disk, key=lambda f: (RES_RANK.get(f["res"], 5), -f["size"])), "arr-tracked"
    # arr knows nothing here: keep the preferred resolution, largest on a tie
    return min(files, key=lambda f: (RES_RANK.get(f["res"], 5), -f["size"])), "resolution-preference"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually move duplicates to quarantine")
    ap.add_argument("--root", help="override library root (for self-test)")
    ap.add_argument("--downloads", help="override downloads root (for self-test)")
    args = ap.parse_args()

    global MOVIES, SHOWS, DOWNLOADS
    if args.root:
        MOVIES, SHOWS = os.path.join(args.root, "movies"), os.path.join(args.root, "shows")
    if args.downloads:
        DOWNLOADS = args.downloads

    env = load_env()
    tracked = arr_tracked_paths(env) if not args.root else set()
    seeded = seeded_inodes() if os.path.isdir(DOWNLOADS) else set()
    day = date.fromtimestamp(os.stat(ENV).st_mtime).isoformat() if args.root else _today()
    trashday = os.path.join(TRASH, day)
    manifest = os.path.join(trashday, "manifest.jsonl")

    dup_groups = removed = skipped_seed = kept_back = 0
    reclaimed = 0
    for label, files in groups():
        # collapse hardlink-identical entries (same physical file) — not a real duplicate
        uniq = {}
        for f in files:
            uniq.setdefault(f["key"], f)
        files = list(uniq.values())
        if len(files) < 2:
            continue
        dup_groups += 1
        keeper, why = pick_keeper(files, tracked)
        print(f"\n[{label}] {len(files)} versions — keep {keeper['res']} ({why}): {os.path.basename(keeper['path'])}")
        for f in files:
            if f["key"] == keeper["key"]:
                continue
            if f["key"] in seeded:
                print(f"    SEEDING, leaving in place: {f['res']:>6}  {os.path.basename(f['path'])}")
                skipped_seed += 1
                kept_back += 1
                continue
            rel = os.path.relpath(f["path"], MOVIES if label.startswith("movie:") else SHOWS)
            dest = os.path.join(trashday, "movies" if label.startswith("movie:") else "shows", rel)
            print(f"    {'QUARANTINE' if args.apply else 'would quarantine'}: {f['res']:>6}  {os.path.basename(f['path'])}  ({f['size']/1e9:.2f} GB)")
            if args.apply:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(f["path"], dest)
                with open(manifest, "a") as mf:
                    mf.write(json.dumps({"orig": f["path"], "quarantined": dest, "size": f["size"],
                                         "group": label, "keeper": keeper["path"], "when": _now()}) + "\n")
            removed += 1
            reclaimed += f["size"]
        # 720p-preference note without re-grabbing
        if keeper["res"] != "720p" and any(f["res"] == "720p" for f in files):
            print(f"    NOTE: a 720p version exists but keeper is {keeper['res']} (kept to avoid re-download; switch manually if you prefer)")

    if args.apply and os.path.isdir(TRASH):
        _purge_old()

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'} — duplicate groups: {dup_groups} | "
          f"{'quarantined' if args.apply else 'would quarantine'}: {removed} ({reclaimed/1e9:.2f} GB) | "
          f"left seeding: {skipped_seed}")
    if not args.apply and removed:
        print("Re-run with --apply to move them. Restore any file from its manifest.jsonl entry.")


def _today():
    return time.strftime("%Y-%m-%d", time.localtime())


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _purge_old():
    cutoff = time.time() - RETAIN_DAYS * 86400
    for d in os.listdir(TRASH):
        p = os.path.join(TRASH, d)
        if os.path.isdir(p) and os.stat(p).st_mtime < cutoff:
            shutil.rmtree(p, ignore_errors=True)
            print(f"purged expired quarantine: {d}")


if __name__ == "__main__":
    main()
