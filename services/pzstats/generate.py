#!/usr/bin/env python3
"""Build stats.json for the Project Zomboid status page.

Reads three sources and merges them:
  A2S query        - live: is it up, who is on right now
  PerkLog.txt      - in-game hours survived and skill levels per character
  *_user.txt       - join/leave pairs, giving real-world playtime

Deliberately publishes no Steam IDs and no chat contents; this page is
reachable by anyone who knows the URL.
"""
from __future__ import annotations

import colorsys
import glob
import hashlib
import json
import os
import re
import socket
import struct
import sys
from collections import defaultdict
from datetime import datetime, timezone

VOLUME = "/var/lib/pterodactyl/volumes/16701806-de59-4dc1-b913-cf5022fbab7d"
LOGS = f"{VOLUME}/.cache/Logs"
SAVE = f"{VOLUME}/.cache/Saves/Multiplayer/servertest"
OUT = "/home/noah/pzstats/www/stats.json"
LIVE = "/home/noah/pzstats/www/live.json"

# Logs older than the current world describe a world that no longer exists.
WORLD_EPOCH = "2026-08-11_14-51"

A2S_HOST, A2S_PORT = "192.168.1.211", 16261


def a2s_info(host: str, port: int) -> dict:
    """Live server info. Returns {'online': False} rather than raising."""
    q = b"\xff\xff\xff\xffTSource Engine Query\x00"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.5)
    try:
        s.sendto(q, (host, port))
        d, _ = s.recvfrom(4096)
        if d[4:5] == b"A":                      # challenge, retry with it
            s.sendto(q + d[5:9], (host, port))
            d, _ = s.recvfrom(4096)
        b = d[6:]

        def sz() -> str:
            nonlocal b
            i = b.index(b"\x00")
            v = b[:i].decode("utf8", "replace")
            b = b[i + 1:]
            return v

        name, mapname = sz(), sz()
        sz(); sz()                              # folder, game
        b = b[2:]                               # appid
        return {"online": True, "name": name, "map": mapname,
                "players": b[0], "max": b[1]}
    except (socket.timeout, OSError, IndexError, ValueError):
        return {"online": False}
    finally:
        s.close()


def a2s_players(host: str, port: int) -> list[dict]:
    """Who is connected right now: [{'name':..., 'secs':...}], newest last.

    PZ answers A2S_PLAYER with real usernames and connection duration, so this
    is the only source of "who is on" that is actually live - players.db only
    catches up on the hourly world save.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.5)
    try:
        s.sendto(b"\xff\xff\xff\xffU\xff\xff\xff\xff", (host, port))
        d, _ = s.recvfrom(8192)
        if d[4:5] == b"A":                      # challenge, retry with it
            s.sendto(b"\xff\xff\xff\xffU" + d[5:9], (host, port))
            d, _ = s.recvfrom(8192)
        if d[4:5] != b"D":
            return []
        out, b = [], d[6:]
        for _ in range(d[5]):
            b = b[1:]                           # per-player index, unused
            i = b.index(b"\x00")
            name = b[:i].decode("utf8", "replace")
            b = b[i + 1:]
            _score, secs = struct.unpack("<if", b[:8])
            b = b[8:]
            if name:
                out.append({"name": name, "secs": round(secs)})
        return out
    except (socket.timeout, OSError, IndexError, ValueError, struct.error):
        return []
    finally:
        s.close()


def log_files(suffix: str) -> list[str]:
    """Matching logs oldest first. Sorted by BASENAME - the session stamp - because
    PZ leaves the running session at the top of Logs/ and archives older ones into
    logs_<date>/ subdirectories, so a path sort would order them by directory."""
    files = glob.glob(os.path.join(LOGS, "**", f"*{suffix}"), recursive=True)
    return sorted((f for f in files if os.path.basename(f) >= WORLD_EPOCH),
                  key=os.path.basename)


PERK_EVENT = re.compile(
    r"\[([\d-]+ [\d:.]+)\]\s*\[(\d+)\]\[([^\]]+)\]\[[^\]]*\]\[(Login|Logout)\]"
    r"\[Hours Survived: (\d+)\]")
PERK_SKILLS = re.compile(
    r"\[([\d-]+ [\d:.]+)\]\s*\[(\d+)\]\[([^\]]+)\]\[[^\]]*\]\[([A-Za-z]+=\d+.*)\]")
JOIN = re.compile(r'\[([\d-]+ [\d:.]+)\] \d+ "([^"]+)" allowed to join')
LEAVE = re.compile(r'\[([\d-]+ [\d:.]+)\] \d+ "([^"]+)" disconnected player')

USER_EVENT = re.compile(
    r'\[([\d-]+ [\d:.]+)\] \d+ "([^"]+)" (allowed to join|fully connected|disconnected player)')
CONN_EVENT = re.compile(
    r'\[([\d-]+ [\d:.]+)\].*message="(fully-connected|player-connect|receive-disconnect'
    r'|connection-lost)".*username="([^"]+)"')
JOIN_EVENTS = {"allowed to join", "fully connected", "fully-connected", "player-connect"}


def online_from_logs() -> list[dict]:
    """[{'name','secs'}] for everyone the server's own logs say is connected.

    A2S_PLAYER only lists players the server registered with Steam, which on this
    box is a subset - anyone who typed the address into Join a Server never shows
    up there. The connection logs see every join, so they are the real roster.
    Both files of the newest session are read: _user.txt has the clean join/leave
    lines, _connections.txt adds the RakNet drops for clients that died without
    saying goodbye.
    """
    sessions = log_files("_user.txt")
    if not sessions:
        return []
    base = sessions[-1][:-len("_user.txt")]
    last: dict[str, tuple[datetime, bool]] = {}
    joined: dict[str, datetime] = {}
    for path, pat, name_first in ((base + "_user.txt", USER_EVENT, True),
                                  (base + "_connections.txt", CONN_EVENT, False)):
        try:
            fh = open(path, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                m = pat.search(line)
                if not m:
                    continue
                stamp, a, b = m.groups()
                name, event = (a, b) if name_first else (b, a)
                if name == "null":
                    continue
                try:
                    t = parse_ts(stamp)
                except ValueError:
                    continue
                if name not in last or last[name][0] <= t:
                    last[name] = (t, event in JOIN_EVENTS)
                if event in JOIN_EVENTS:
                    joined[name] = t
    now = datetime.now()
    out = [{"name": n, "secs": max(0, round((now - joined.get(n, t)).total_seconds()))}
           for n, (t, is_on) in last.items() if is_on]
    return sorted(out, key=lambda p: -p["secs"])


def who_is_online(server: dict) -> list[dict]:
    """Log roster, falling back to A2S if the logs are unreadable (they are NFS)."""
    if not server.get("online"):
        return []
    return online_from_logs() or a2s_players(A2S_HOST, A2S_PORT)


# ---- character appearance -------------------------------------------------
# PZ has no render API and the humanVisual colours are binary floats, but the
# worn item IDs survive as plain strings in the save blob, so the avatar can be
# tinted by what someone is actually wearing instead of being invented.
PLAYERS_DB = f"{SAVE}/players.db"
WEARABLE = re.compile(
    rb"Base\.((?:Shirt|Tshirt|TShirt|Trousers|Shoes|Jacket|Hat|Vest|Skirt|Dress|Sweater"
    rb"|Hoodie|Jeans|Shorts|Bag|Gloves|Glasses|Coat|Suit|Socks|Belt|Boots|Mask|Scarf|Cap)"
    rb"[A-Za-z_]*)")

# item fragment -> tint. First match wins, so put specific before generic.
TOPS = [("Chef", "#f2f2f0"), ("Suit_Jacket", "#232733"), ("Jacket_Black", "#1c1c20"),
        ("Vest_BulletPolice", "#2b3340"), ("Jacket", "#5a4632"), ("Scrubs", "#3f8f86"),
        ("Hoodie", "#4a4f57"), ("Sweater", "#6b4a3a"), ("FormalWhite", "#e9e9e6"),
        ("Polo", "#c9d3dc"), ("WhiteLongSleeve", "#dedede"), ("White", "#dedede")]
# a plain shirt says nothing about a person, so those fall through to the
# name-derived hue instead and everyone stays visually distinct


def _pick(table: list[tuple[str, str]], items: list[str]) -> str | None:
    for frag, colour in table:
        if any(frag.lower() in it.lower() for it in items):
            return colour
    return None


def worn_by_player() -> dict[str, list[str]]:
    """{username: [worn item ids]} from the save database."""
    out: dict[str, list[str]] = {}
    if not os.path.exists(PLAYERS_DB):
        return out
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{PLAYERS_DB}?mode=ro", uri=True)
        rows = con.execute("SELECT username, data FROM networkPlayers").fetchall()
        con.close()
    except Exception:                      # save locked mid-write, or schema changed
        return out
    for username, blob in rows:
        if not blob:
            continue
        items, seen = [], set()
        for m in WEARABLE.finditer(blob):
            it = m.group(1).decode("ascii", "replace")
            if it not in seen:
                seen.add(it)
                items.append(it)
        out[username] = items
    return out


def saved_positions() -> tuple[dict[str, dict], str]:
    """{username: {x, y, dead}} plus when the save wrote them.

    The server only flushes player rows on its hourly world save, so these are
    last-known positions, not live ones - the page says so.
    """
    out: dict[str, dict] = {}
    when = ""
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{PLAYERS_DB}?mode=ro", uri=True)
        for u, x, y, dead in con.execute(
                "SELECT username,x,y,isDead FROM networkPlayers"):
            out[u] = {"x": round(x or 0), "y": round(y or 0), "dead": bool(dead)}
        con.close()
        when = datetime.fromtimestamp(
            os.path.getmtime(PLAYERS_DB), timezone.utc).isoformat(timespec="seconds")
    except Exception:                      # save locked mid-write, or schema changed
        pass
    return out, when


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def _hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in (r, g, b))


def _lum(hex_colour: str) -> float:
    r, g, b = _rgb(hex_colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _clamp_lum(hex_colour: str, lo: float, hi: float) -> str:
    """Push a colour into a luminance band so the white monogram always reads."""
    lum = _lum(hex_colour)
    if not lum:                        # black has no chroma to scale, so go grey
        return _hex(lo, lo, lo)
    k = (lo / lum) if lum < lo else (hi / lum) if lum > hi else 1.0
    if k == 1.0:
        return hex_colour
    return _hex(*(c * k for c in _rgb(hex_colour)))


def _shade(hex_colour: str, k: float) -> str:
    return _hex(*(c * k for c in _rgb(hex_colour)))


def _slug(name: str) -> str:
    """Stable id fragment - SVG gradient ids share one document namespace."""
    return re.sub(r"[^a-z0-9]", "", name.lower())[:12] or "x"


def base_colour(items: list[str], name: str) -> str:
    """Tint from the worn top layer; failing that, a stable hue from the name."""
    worn = _pick(TOPS, items)
    if worn:
        return _clamp_lum(worn, 62, 132)
    h = (int(hashlib.sha1(name.encode("utf8")).hexdigest()[:6], 16) % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(h, 0.36, 0.34)
    return _hex(r * 255, g * 255, b * 255)


def avatar_svg(items: list[str], name: str, arc: float = 0.0) -> str:
    """A 56px monogram disc: garment-tinted gradient, survival ring around it.

    Nothing is invented - the tint comes from what the save says they wear, and
    the ring is their survival time against the longest on the server.
    """
    base = base_colour(items, name)
    top, bot = _shade(base, 1.34), _shade(base, 0.55)
    sid = _slug(name)
    ch = 2 * 3.14159265 * 26.5                     # ring circumference at r=26.5
    on = max(0.0, min(1.0, arc)) * ch
    initial = (re.sub(r"[^0-9A-Za-z]", "", name)[:1] or "?").upper()

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60" width="60" '
        f'height="60" role="img" aria-label="{initial}">'
        f'<defs><linearGradient id="g{sid}" x1="0" y1="0" x2=".35" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bot}"/>'
        f'</linearGradient></defs>'
        f'<circle cx="30" cy="30" r="23" fill="url(#g{sid})"/>'
        f'<circle cx="30" cy="30" r="23" fill="none" stroke="#fff" stroke-opacity=".14"/>'
        f'<text x="30" y="30.5" text-anchor="middle" dominant-baseline="central" '
        f'font-family="ui-monospace,Menlo,Consolas,monospace" font-size="21" '
        f'font-weight="600" fill="#fff" fill-opacity=".95">{initial}</text>'
        f'<circle cx="30" cy="30" r="26.5" fill="none" stroke="#fff" stroke-opacity=".08" '
        f'stroke-width="2.5"/>'
        f'<circle cx="30" cy="30" r="26.5" fill="none" stroke="#e21e37" stroke-width="2.5" '
        f'stroke-linecap="round" stroke-dasharray="{on:.1f} {ch - on:.1f}" '
        f'transform="rotate(-90 30 30)"/>'
        f'</svg>')


def pretty(item: str) -> str:
    """Base item id -> something readable in a tooltip."""
    s = re.sub(r"(TINT|TEXTURE)", "", item)
    s = s.replace("_", " ").strip()
    return re.sub(r"(?<!^)(?=[A-Z])", " ", s).replace("  ", " ").strip()


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s.split(".")[0], "%d-%m-%y %H:%M:%S")


# ---- world map + activity ------------------------------------------------
CELL = 300          # a PZ cell is 300x300 world tiles
CHUNKDATA = f"{SAVE}/chunkdata"
HISTORY = "/home/noah/pzstats/www/history.json"

# Muldraugh-area landmarks, for orientation on the explored map
LANDMARKS = [
    (10600, 9600, "Muldraugh"),
    (12800, 7100, "West Point"),
    (8000, 11500, "Rosewood"),
    (6500, 5500, "Riverside"),
    (13000, 3200, "March Ridge"),
]


def explored_cells() -> list[list[int]]:
    """[[cellX, cellY], ...] - which 300x300 cells the world has generated."""
    out = []
    try:
        for fn in os.listdir(CHUNKDATA):
            m = re.match(r"chunkdata_(\d+)_(\d+)\.bin$", fn)
            if m:
                out.append([int(m.group(1)), int(m.group(2))])
    except OSError:
        pass
    return sorted(out)


def activity_by_hour(events: list) -> list[int]:
    """24 buckets: how many sessions started in each hour of the day."""
    hours = [0] * 24
    for t, _name, kind in events:
        if kind == "in":
            hours[t.hour] += 1
    return hours


def append_history(snapshot: dict) -> None:
    """Keep a small rolling series so the page can chart trends.

    One point per run, capped - this is a few KB, not a database.
    """
    try:
        hist = json.load(open(HISTORY, encoding="utf-8"))
    except (OSError, ValueError):
        hist = []
    hist.append(snapshot)
    # 1 point/min, keep ~7 days
    hist = hist[-10080:]
    tmp = HISTORY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(hist, fh, separators=(",", ":"))
    os.replace(tmp, HISTORY)
    os.chmod(HISTORY, 0o644)


def collect() -> dict:
    hours: dict[str, int] = defaultdict(int)
    skills: dict[str, tuple[str, str]] = {}
    last_seen: dict[str, str] = {}

    for f in log_files("PerkLog.txt"):
        for line in open(f, errors="replace"):
            m = PERK_EVENT.search(line)
            if m:
                ts, _sid, name, _kind, h = m.groups()
                hours[name] = max(hours[name], int(h))
                last_seen[name] = ts
                continue
            m = PERK_SKILLS.search(line)
            if m:
                ts, _sid, name, blob = m.groups()
                skills[name] = (ts, blob)

    # real-world playtime from join/leave pairs
    events: list[tuple[datetime, str, str]] = []
    for f in log_files("_user.txt"):
        for line in open(f, errors="replace"):
            m = JOIN.search(line)
            if m:
                events.append((parse_ts(m.group(1)), m.group(2), "in"))
                continue
            m = LEAVE.search(line)
            if m:
                events.append((parse_ts(m.group(1)), m.group(2), "out"))
    events.sort()

    seconds: dict[str, float] = defaultdict(float)
    sessions: dict[str, int] = defaultdict(int)
    open_at: dict[str, datetime] = {}
    for t, name, kind in events:
        if kind == "in":
            open_at[name] = t
        elif name in open_at:
            seconds[name] += (t - open_at.pop(name)).total_seconds()
            sessions[name] += 1
    # a session with no matching leave is still running (or the server died);
    # count it up to the last event we saw so the number is never silently short
    if events:
        end = events[-1][0]
        for name, t0 in open_at.items():
            seconds[name] += (end - t0).total_seconds()
            sessions[name] += 1

    worn = worn_by_player()
    positions, pos_saved = saved_positions()

    server = a2s_info(A2S_HOST, A2S_PORT)
    online = who_is_online(server)
    if server.get("online"):
        server["players"] = len(online)      # A2S undercounts; the logs do not
    live_now = {p["name"] for p in online}
    top_hours = max(hours.values(), default=0) or 1

    players = []
    for name in sorted(set(hours) | set(skills) | set(seconds),
                       key=lambda n: -seconds.get(n, 0)):
        items = worn.get(name, [])
        outfit = [pretty(i) for i in items
                  if not i.startswith(("Belt", "Socks"))][:6]
        blob = skills.get(name, ("", ""))[1]
        parsed = {}
        for part in blob.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    parsed[k] = int(v)
                except ValueError:
                    pass
        players.append({
            "name": name,
            "hours_survived": hours.get(name, 0),
            "playtime_hours": round(seconds.get(name, 0) / 3600, 1),
            "sessions": sessions.get(name, 0),
            "last_seen": last_seen.get(name, ""),
            "skills": {k: v for k, v in sorted(parsed.items(), key=lambda x: -x[1]) if v > 0},
            "total_skill": sum(parsed.values()),
            "avatar": avatar_svg(items, name, hours.get(name, 0) / top_hours),
            "outfit": outfit,
            "outfit_full": [pretty(i) for i in items],
            "pos": positions.get(name),
            "online": name in live_now,
        })

    cells = explored_cells()
    hours = activity_by_hour(events)

    world_bytes = 0
    for root, _dirs, files in os.walk(SAVE):
        for fn in files:
            try:
                world_bytes += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass

    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server": server,
        "positions_saved": pos_saved,
        "players": players,
        "world": {
            "size_mb": round(world_bytes / 1048576, 1),
            "chunks": len(cells),
            "combined_playtime_hours": round(sum(seconds.values()) / 3600, 1),
            "cell_size": CELL,
            "cells": cells,
            "landmarks": [{"x": x, "y": y, "name": n} for x, y, n in LANDMARKS],
            "activity_by_hour": hours,
        },
    }


def write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":") if path == LIVE else None,
                  indent=None if path == LIVE else 1)
    os.replace(tmp, path)         # atomic: readers never see a half-written file
    os.chmod(path, 0o644)


def live() -> dict:
    """The cheap slice that can be polled every few seconds (~6ms to build)."""
    positions, pos_saved = saved_positions()
    server = a2s_info(A2S_HOST, A2S_PORT)
    online = who_is_online(server)
    if server.get("online"):
        server["players"] = len(online)      # A2S undercounts; the logs do not
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server": server,
        "online": online,
        "positions": positions,
        "positions_saved": pos_saved,
    }


def selftest() -> None:
    """The bits that would fail silently: the binary parse and the colour band."""
    body = b"\x00LUMBERJACKSON\x00" + struct.pack("<if", 0, 4212.0) \
         + b"\x01Rosinfools\x00" + struct.pack("<if", 0, 2236.0)
    reply = b"\xff\xff\xff\xffD\x02" + body
    sock = type("S", (), {"sendto": lambda *a: None, "recvfrom": lambda *a: (reply, None),
                          "settimeout": lambda *a: None, "close": lambda *a: None})
    orig, socket.socket = socket.socket, lambda *a: sock()
    try:
        got = a2s_players("x", 0)
    finally:
        socket.socket = orig
    assert got == [{"name": "LUMBERJACKSON", "secs": 4212},
                   {"name": "Rosinfools", "secs": 2236}], got

    # the band is per-channel rounded, so allow a point of slack either side
    assert 61 <= _lum(_clamp_lum("#000000", 62, 132)) <= 133      # black cannot be scaled
    assert 61 <= _lum(_clamp_lum("#1c1c20", 62, 132)) <= 133      # dark tops get lifted
    assert 61 <= _lum(_clamp_lum("#f2f2f0", 62, 132)) <= 133      # bright tops get pulled down
    assert _clamp_lum("#5a4632", 62, 132) == "#5a4632"            # in-band colours untouched
    assert base_colour([], "Yote") == base_colour([], "Yote")     # hue is stable per name
    assert base_colour([], "Yote") != base_colour([], "Rosin")
    assert 'dasharray="0.0' in avatar_svg([], "x", 0)             # empty ring at zero
    assert "?" in avatar_svg([], "!!!", 0)                        # nameless still renders

    import tempfile
    global LOGS
    keep, tmp = LOGS, tempfile.mkdtemp()
    try:
        LOGS = tmp
        old_dir = os.path.join(tmp, "logs_2026-08-12")   # an archived, finished session
        os.mkdir(old_dir)
        stamp = datetime.now().strftime("%d-%m-%y %H:%M:%S")
        open(os.path.join(old_dir, "2026-08-11_20-00_user.txt"), "w").write(
            f'[{stamp}.000] 1 "GhostFromLastSession" allowed to join.\n')
        # the running session sits at the top of Logs/, where a path sort buries it
        open(os.path.join(tmp, "2026-08-12_23-10_user.txt"), "w").write(
            f'[{stamp}.000] 1 "Stayed" fully connected (1,2,0).\n'
            f'[{stamp}.000] 2 "Left" allowed to join.\n'
            f'[{stamp}.000] 2 "Left" disconnected player (1,2,0).\n'
            f'[{stamp}.000] 3 "Crashed" fully connected (1,2,0).\n')
        open(os.path.join(tmp, "2026-08-12_23-10_connections.txt"), "w").write(
            f'[{stamp}.000] event="RakNet" message="connection-lost" username="Crashed".\n')
        names = [p["name"] for p in online_from_logs()]
        assert names == ["Stayed"], names       # not Left, not Crashed, not the ghost
        assert who_is_online({"online": False}) == []
    finally:
        LOGS = keep
        __import__("shutil").rmtree(tmp, ignore_errors=True)
    print("selftest ok")


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if "--selftest" in sys.argv:
        return selftest()
    if "--live" in sys.argv:
        write_json(LIVE, live())
        return
    data = collect()
    append_history({
        "t": data["generated"],
        "online": data["server"].get("players", 0) if data["server"].get("online") else None,
        "hours": data["world"]["combined_playtime_hours"],
    })
    write_json(OUT, data)
    write_json(LIVE, live())
    print(f"wrote {OUT}: {len(data['players'])} players, "
          f"server {'up' if data['server'].get('online') else 'down'}")


if __name__ == "__main__":
    sys.exit(main())
