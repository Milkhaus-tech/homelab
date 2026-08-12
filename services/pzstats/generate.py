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

import glob
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

# Logs older than the current world describe a world that no longer exists.
WORLD_EPOCH = "2026-08-11_14-51"

A2S_HOST, A2S_PORT = "127.0.0.1", 16261


def a2s_info(host: str, port: int) -> dict:
    """Live server info. Returns {'online': False} rather than raising."""
    q = b"\xff\xff\xff\xffTSource Engine Query\x00"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(4)
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


def log_files(suffix: str) -> list[str]:
    files = glob.glob(os.path.join(LOGS, "**", f"*{suffix}"), recursive=True)
    return sorted(f for f in files if os.path.basename(f) >= WORLD_EPOCH)


PERK_EVENT = re.compile(
    r"\[([\d-]+ [\d:.]+)\]\s*\[(\d+)\]\[([^\]]+)\]\[[^\]]*\]\[(Login|Logout)\]"
    r"\[Hours Survived: (\d+)\]")
PERK_SKILLS = re.compile(
    r"\[([\d-]+ [\d:.]+)\]\s*\[(\d+)\]\[([^\]]+)\]\[[^\]]*\]\[([A-Za-z]+=\d+.*)\]")
JOIN = re.compile(r'\[([\d-]+ [\d:.]+)\] \d+ "([^"]+)" allowed to join')
LEAVE = re.compile(r'\[([\d-]+ [\d:.]+)\] \d+ "([^"]+)" disconnected player')

# ---- character appearance -------------------------------------------------
# PZ has no render API and the humanVisual colours are binary floats, but the
# worn item IDs survive as plain strings in the save blob. That is enough to
# draw a paper doll that tracks what someone is actually wearing.
PLAYERS_DB = f"{SAVE}/players.db"
WEARABLE = re.compile(
    rb"Base\.((?:Shirt|Tshirt|TShirt|Trousers|Shoes|Jacket|Hat|Vest|Skirt|Dress|Sweater"
    rb"|Hoodie|Jeans|Shorts|Bag|Gloves|Glasses|Coat|Suit|Socks|Belt|Boots|Mask|Scarf|Cap)"
    rb"[A-Za-z_]*)")
HAIR = re.compile(rb"\b(MohawkSpike|Mohawk|Ponytail|Dreadlocks|Afro|CrewCut|Bald|Buzz"
                  rb"|LongRough|Long|Short|Messy|Curly|Bun|Pigtails)\b")

# item fragment -> fill. First match wins, so put specific before generic.
TOPS = [("Chef", "#f2f2f0"), ("Suit_Jacket", "#232733"), ("Jacket_Black", "#1c1c20"),
        ("Vest_BulletPolice", "#2b3340"), ("Jacket", "#5a4632"), ("Scrubs", "#3f8f86"),
        ("Hoodie", "#4a4f57"), ("Sweater", "#6b4a3a"), ("FormalWhite", "#e9e9e6"),
        ("Polo", "#c9d3dc"), ("WhiteLongSleeve", "#dedede"), ("White", "#dedede"),
        ("Shirt", "#b9c2cb"), ("Tshirt", "#b9c2cb")]
LEGS = [("Trousers_Suit", "#2a2e39"), ("Denim", "#3f5a7a"), ("Crafted", "#6a5540"),
        ("Shorts", "#7a6a52"), ("Jeans", "#3f5a7a"), ("Trousers", "#4a4f57"),
        ("Skirt", "#6b3a4a")]
FEET = [("ArmyBoots", "#3a3227"), ("BlackBoots", "#232323"), ("BlueTrainers", "#3f6fae"),
        ("Trainer", "#d8d8d8"), ("Boots", "#3a3227"), ("Shoes", "#4a4038")]
HATS = [("RiotHelmet", "#2f3336"), ("Cap", "#7a3a3a"), ("WoolyHat", "#7a3a3a"), ("Hat", "#6b5a3a")]


def _pick(table: list[tuple[str, str]], items: list[str], default: str) -> str | None:
    for frag, colour in table:
        if any(frag.lower() in it.lower() for it in items):
            return colour
    return default


def worn_by_player() -> dict[str, dict]:
    """{username: {'items': [...], 'hair': str|None}} from the save database."""
    out: dict[str, dict] = {}
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
        h = HAIR.search(blob)
        out[username] = {"items": items, "hair": h.group(1).decode() if h else None}
    return out


def avatar_svg(items: list[str], hair: str | None) -> str:
    """A 40x56 paper doll coloured by what the character has on."""
    top = _pick(TOPS, items, "#8d949c")
    legs = _pick(LEGS, items, "#4a4f57")
    feet = _pick(FEET, items, "#3a3327")
    hat = _pick(HATS, items, None) if any(
        any(f.lower() in it.lower() for f, _ in HATS) for it in items) else None
    bag = any("Bag" in it for it in items)
    glasses = any("Glasses" in it for it in items)
    skin, hairc = "#e3b998", "#3a2b22"

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 56" width="40" height="56">']
    p.append('<rect width="40" height="56" rx="5" fill="#1b1e22"/>')
    if bag:                                     # strap over the shoulder
        p.append('<rect x="9" y="24" width="22" height="15" rx="3" fill="#2f3540"/>')
    p.append(f'<rect x="12" y="39" width="6" height="10" fill="{legs}"/>')
    p.append(f'<rect x="22" y="39" width="6" height="10" fill="{legs}"/>')
    p.append(f'<rect x="11" y="48" width="8" height="4" rx="1.5" fill="{feet}"/>')
    p.append(f'<rect x="21" y="48" width="8" height="4" rx="1.5" fill="{feet}"/>')
    p.append(f'<rect x="10" y="23" width="20" height="17" rx="3" fill="{top}"/>')
    p.append(f'<rect x="6" y="24" width="5" height="13" rx="2.5" fill="{top}"/>')
    p.append(f'<rect x="29" y="24" width="5" height="13" rx="2.5" fill="{top}"/>')
    p.append(f'<circle cx="20" cy="15" r="8" fill="{skin}"/>')
    if hair and hair.lower() != "bald":
        if "mohawk" in hair.lower():
            p.append(f'<rect x="18" y="4" width="4" height="8" rx="2" fill="{hairc}"/>')
        else:
            p.append(f'<path d="M12 13 A8 8 0 0 1 28 13 L28 10 A8 8 0 0 0 12 10 Z" fill="{hairc}"/>')
    if hat:
        p.append(f'<path d="M11 12 A9 9 0 0 1 29 12 L29 14 L11 14 Z" fill="{hat}"/>')
    if glasses:
        p.append('<rect x="14" y="13" width="12" height="3" rx="1.5" fill="#20242a" opacity=".85"/>')
    p.append('<circle cx="17" cy="15" r="1" fill="#2b2b2b"/><circle cx="23" cy="15" r="1" fill="#2b2b2b"/>')
    p.append("</svg>")
    return "".join(p)


def pretty(item: str) -> str:
    """Base item id -> something readable in a tooltip."""
    s = re.sub(r"(TINT|TEXTURE)", "", item)
    s = s.replace("_", " ").strip()
    return re.sub(r"(?<!^)(?=[A-Z])", " ", s).replace("  ", " ").strip()


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s.split(".")[0], "%d-%m-%y %H:%M:%S")


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

    players = []
    for name in sorted(set(hours) | set(skills) | set(seconds),
                       key=lambda n: -seconds.get(n, 0)):
        look = worn.get(name, {"items": [], "hair": None})
        outfit = [pretty(i) for i in look["items"]
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
            "avatar": avatar_svg(look["items"], look["hair"]),
            "outfit": outfit,
        })

    world_bytes = 0
    for root, _dirs, files in os.walk(SAVE):
        for fn in files:
            try:
                world_bytes += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass

    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server": a2s_info(A2S_HOST, A2S_PORT),
        "players": players,
        "world": {
            "size_mb": round(world_bytes / 1048576, 1),
            "chunks": len(os.listdir(f"{SAVE}/chunkdata")) if os.path.isdir(f"{SAVE}/chunkdata") else 0,
            "combined_playtime_hours": round(sum(seconds.values()) / 3600, 1),
        },
    }


def main() -> None:
    data = collect()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, OUT)          # atomic: readers never see a half-written file
    os.chmod(OUT, 0o644)
    print(f"wrote {OUT}: {len(data['players'])} players, "
          f"server {'up' if data['server'].get('online') else 'down'}")


if __name__ == "__main__":
    sys.exit(main())
