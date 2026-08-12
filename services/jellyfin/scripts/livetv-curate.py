#!/usr/bin/env python3
"""Build Jellyfin's curated Live TV lineup from free FAST feeds.

Fetches BuddyChewChew playlists + i.mjh.nz EPGs (Pluto/Samsung/Roku),
filters to LINEUP below, renumbers by bucket, writes curated.m3u +
merged guide.xml into jellyfin's /config/livetv/, then triggers a
Jellyfin guide refresh. Edit LINEUP to add/drop channels (names must
match the source playlist exactly; misses are logged, not fatal).
Run with --selftest for policy checks. Cron: twice daily.
"""
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

OUT_DIR = '/home/noah/docker/jellyfin/config/livetv'
JF_URL = 'http://localhost:8096'
JF_KEYFILE = '/home/noah/docker/qbittorrentvpn/config/jellyseerr/settings.json'

PL = 'https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists'
SOURCES = {
    'pluto':   (f'{PL}/plutotv_us.m3u',       'https://i.mjh.nz/PlutoTV/us.xml.gz'),
    'samsung': (f'{PL}/samsungtvplus_us.m3u', 'https://i.mjh.nz/SamsungTVPlus/us.xml.gz'),
    'roku':    (f'{PL}/roku_all.m3u',         'https://i.mjh.nz/Roku/all.xml.gz'),
}

BUCKETS = {1: 'Sports', 2: 'News', 3: 'Entertainment', 4: 'Anime', 5: 'Music'}

LINEUP = [
    # --- 100s Sports ---
    (101, 'pluto', 'NFL Channel'),
    (102, 'pluto', 'MLB'),
    (103, 'pluto', 'The NBA Channel'),
    (104, 'pluto', 'FOX Sports'),
    (105, 'pluto', 'CBS Sports HQ'),
    (106, 'pluto', 'NBC Sports NOW'),
    (107, 'samsung', 'beIN SPORTS XTRA'),
    (108, 'samsung', 'CBS Sports Golazo Network'),
    (109, 'pluto', 'UEFA Champions League'),
    (110, 'samsung', 'FIFA+'),
    (111, 'samsung', 'ESPN8: The Ocho'),
    (112, 'samsung', 'fubo Sports Network'),
    (113, 'samsung', 'Stadium'),
    (114, 'samsung', 'UFC'),
    (115, 'pluto', 'PFL MMA'),
    (116, 'pluto', 'TNA Wrestling'),
    (117, 'pluto', 'PGA TOUR'),
    (118, 'pluto', 'TennisChannel 2'),
    (119, 'samsung', 'NASCAR Channel'),
    (120, 'samsung', 'Formula 1 Channel'),
    (121, 'samsung', 'MotoGP Channel'),
    (122, 'roku', 'Red Bull TV'),
    (123, 'roku', 'X Games TV'),
    (124, 'pluto', "Women's Sports Network"),
    # --- 200s News ---
    (201, 'pluto', 'ABC News Live'),
    (202, 'pluto', 'NBC News NOW'),
    (203, 'pluto', 'CBS News 24/7'),
    (204, 'pluto', 'LiveNOW from FOX'),
    (205, 'pluto', 'Scripps News'),
    (206, 'pluto', 'BBC News'),
    (207, 'pluto', 'Sky News'),
    (208, 'pluto', 'Bloomberg TV+'),
    (209, 'samsung', 'Yahoo Finance'),
    (210, 'samsung', 'The Hill'),
    (211, 'pluto', 'FOX Weather'),
    (212, 'pluto', 'CBS News Los Angeles'),
    (213, 'pluto', 'FOX LOCAL Los Angeles'),
    (214, 'pluto', 'NBC Los Angeles News'),
    # --- 300s Entertainment / cable feel ---
    (301, 'pluto', 'Comedy Central Pluto TV'),
    (302, 'pluto', 'MST3K'),
    (303, 'pluto', 'RiffTrax'),
    (304, 'samsung', "Conan O'Brien TV"),
    (305, 'samsung', 'Hot Ones'),
    (306, 'samsung', 'MrBeast'),
    (307, 'pluto', 'Bar Rescue'),
    (308, 'pluto', "Gordon Ramsay's Hell's Kitchen"),
    (309, 'samsung', 'Kitchen Nightmares'),
    (310, 'pluto', 'Best of Bobby Flay by Food Network'),
    (311, 'pluto', "America's Test Kitchen"),
    (312, 'pluto', 'Forensic Files'),
    (313, 'pluto', 'Unsolved Mysteries'),
    (314, 'pluto', 'COPS'),
    (315, 'pluto', 'Star Trek'),
    (316, 'pluto', 'The Twilight Zone'),
    (317, 'pluto', 'The X-Files'),
    (318, 'pluto', 'BBC Earth'),
    (319, 'samsung', 'Modern Marvels Presented by History'),
    (320, 'samsung', 'Pawn Stars'),
    (321, 'samsung', 'Top Gear'),
    (322, 'pluto', 'The Bob Ross Channel'),
    # --- 400s Anime ---
    (401, 'pluto', 'Crunchyroll'),
    (402, 'pluto', 'ANIME x HIDIVE'),
    (403, 'pluto', 'Pluto TV Anime'),
    (404, 'pluto', 'Pluto TV Anime Movies'),
    (405, 'pluto', 'Naruto'),
    (406, 'pluto', 'One Piece'),
    (407, 'pluto', 'Boruto: Naruto Next Generations'),
    (408, 'pluto', 'Inuyasha'),
    (409, 'pluto', 'Sailor Moon'),
    (410, 'pluto', 'Yu-Gi-Oh!'),
    (411, 'samsung', 'It’s Anime'),
    (412, 'samsung', 'Anime All day'),
    (413, 'samsung', 'RetroCrush'),
    (414, 'samsung', 'Hunter x Hunter'),
    (415, 'samsung', "JoJo's Bizarre Adventure"),
    # --- 500s Music ---
    (501, 'pluto', 'MTV Pluto TV'),
    (502, 'pluto', 'Yo! MTV'),
    (503, 'pluto', 'Vevo Pop'),
    (504, 'pluto', "Vevo '90s"),
    (505, 'pluto', 'Vevo Rock'),
    (506, 'pluto', 'XITE Rock x Metal'),
    (507, 'samsung', 'Stingray Hip Hop'),
    (508, 'pluto', 'Qello Concerts'),
    (509, 'pluto', 'TikTok Radio'),
]


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (livetv-curate)'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if url.endswith('.gz') or data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    return data


def parse_m3u(text):
    """name -> (attr_string, stream_url); first occurrence wins."""
    out = {}
    entries = re.findall(r'#EXTINF:-1([^\n]*),([^\n]+)\n(https?://[^\s]+)', text)
    for attrs, name, url in entries:
        out.setdefault(name.strip(), (attrs, url))
    return out


def attr(attrs, key):
    m = re.search(rf'{key}="([^"]*)"', attrs)
    return m.group(1) if m else ''


def build_m3u(playlists):
    """Return (m3u_text, {source: set(tvg_ids)}). Logs lineup misses."""
    lines = ['#EXTM3U']
    kept = {s: set() for s in SOURCES}
    for num, src, name in LINEUP:
        entry = playlists[src].get(name)
        if not entry:
            print(f'WARNING: [{src}] channel not found upstream: {name!r}')
            continue
        attrs, url = entry
        tvg_id, logo = attr(attrs, 'tvg-id'), attr(attrs, 'tvg-logo')
        if not tvg_id:
            print(f'WARNING: [{src}] {name!r} has no tvg-id; guide will not map')
        else:
            kept[src].add(tvg_id)
        group = BUCKETS[num // 100]
        lines.append(
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-chno="{num}" channel-number="{num}" '
            f'tvg-logo="{logo}" group-title="{group}",{num} {name}')
        lines.append(url)
    return '\n'.join(lines) + '\n', kept


def filter_epg(xml_bytes, keep_ids):
    """Yield (channels, programmes) elements whose id/channel is kept."""
    channels, programmes = [], []
    for _, elem in ET.iterparse(io.BytesIO(xml_bytes)):
        if elem.tag == 'channel' and elem.get('id') in keep_ids:
            channels.append(elem)
        elif elem.tag == 'programme' and elem.get('channel') in keep_ids:
            programmes.append(elem)
    return channels, programmes


def build_guide(epgs, kept):
    tv = ET.Element('tv', {'generator-info-name': 'livetv-curate'})
    total_prog = 0
    for src, xml_bytes in epgs.items():
        channels, programmes = filter_epg(xml_bytes, kept[src])
        for c in channels:
            tv.append(c)
        for p in programmes:
            tv.append(p)
        total_prog += len(programmes)
        print(f'[{src}] guide: {len(channels)} channels, {len(programmes)} programmes')
    return ET.tostring(tv, encoding='unicode'), total_prog


def atomic_write(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(data)
    os.replace(tmp, path)


def refresh_jellyfin_guide():
    key = json.load(open(JF_KEYFILE))['jellyfin']['apiKey']
    hdr = {'Authorization': f'MediaBrowser Token={key}'}
    tasks = json.load(urllib.request.urlopen(
        urllib.request.Request(f'{JF_URL}/ScheduledTasks', headers=hdr)))
    task = next(t for t in tasks if t['Key'] == 'RefreshGuide')
    urllib.request.urlopen(urllib.request.Request(
        f"{JF_URL}/ScheduledTasks/Running/{task['Id']}", headers=hdr, method='POST'))
    print('jellyfin guide refresh triggered')


def run():
    stamp = time.strftime('%F %T')
    print(f'{stamp} fetching sources...')
    playlists, epgs = {}, {}
    for src, (m3u_url, epg_url) in SOURCES.items():
        playlists[src] = parse_m3u(fetch(m3u_url).decode('utf-8', 'replace'))
        epgs[src] = fetch(epg_url)
        print(f'[{src}] {len(playlists[src])} channels upstream')
    m3u, kept = build_m3u(playlists)
    guide, total_prog = build_guide(epgs, kept)
    if total_prog == 0:
        print('ERROR: zero programmes after filtering — keeping previous files')
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)
    atomic_write(os.path.join(OUT_DIR, 'curated.m3u'), m3u)
    atomic_write(os.path.join(OUT_DIR, 'guide.xml'), guide)
    n = m3u.count('#EXTINF')
    print(f'{stamp} wrote {n} channels, {total_prog} programmes -> {OUT_DIR}')
    try:
        refresh_jellyfin_guide()
    except Exception as e:
        print(f'WARNING: guide refresh trigger failed: {e}')


def selftest():
    m3u_text = ('#EXTM3U\n'
                '#EXTINF:-1 tvg-id="id1" tvg-logo="l1" group-title="Sports",Chan One\n'
                'http://x/1.m3u8\n'
                '#EXTINF:-1 tvg-id="id2" group-title="News",Chan Two\n'
                'http://x/2.m3u8\n')
    pl = parse_m3u(m3u_text)
    assert set(pl) == {'Chan One', 'Chan Two'} and pl['Chan One'][1] == 'http://x/1.m3u8'

    global LINEUP
    saved = LINEUP
    LINEUP = [(101, 'pluto', 'Chan One'), (201, 'pluto', 'Missing Chan')]
    try:
        m3u, kept = build_m3u({'pluto': pl, 'samsung': {}, 'roku': {}})
        assert 'tvg-chno="101"' in m3u and '101 Chan One' in m3u, 'renumber+prefix'
        assert 'Missing Chan' not in m3u, 'missing channel skipped'
        assert kept['pluto'] == {'id1'}
    finally:
        LINEUP = saved

    epg = (b'<?xml version="1.0"?><tv>'
           b'<channel id="id1"><display-name>C1</display-name></channel>'
           b'<channel id="idX"><display-name>X</display-name></channel>'
           b'<programme start="1" stop="2" channel="id1"><title>P1</title></programme>'
           b'<programme start="1" stop="2" channel="idX"><title>PX</title></programme>'
           b'</tv>')
    chans, progs = filter_epg(epg, {'id1'})
    assert len(chans) == 1 and len(progs) == 1 and progs[0].find('title').text == 'P1'
    guide, total = build_guide({'pluto': epg}, {'pluto': {'id1'}})
    assert total == 1 and 'idX' not in guide
    print('selftest OK')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
    else:
        run()
