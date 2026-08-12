#!/usr/bin/env python3
"""Reap autobrr-raced torrents (qBittorrent category 'race').

Deletes torrent+files once tracker hit-and-run-safe (10d seedtime) AND
dead (72h no activity) / stopped / past 21d; unfinished races die after 7d.
Also enforces a total disk ceiling for the category (oldest deadest first).
Dry-run by default; --apply deletes; --selftest runs policy checks.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CATEGORY = 'race'
TRACKER_SAFE_HOURS = 240      # tracker hit-and-run clears at 10 days of seeding
DEAD_HOURS = 72          # no swarm activity for this long => dead race
HARD_CAP_HOURS = 504     # 21 days seeded: reclaim even if still trickling
STALE_DL_HOURS = 168     # unfinished for 7 days => race lost, reclaim
DISK_CAP_GB = 500        # ceiling for the whole race category on disk

HRS = 3600.0


def qb_base():
    host = os.environ.get('QB_HOST')
    if not host:
        out = subprocess.run(['ip', '-4', 'addr', 'show', 'tailscale0'],
                             capture_output=True, text=True).stdout
        host = out.split('inet ')[1].split('/')[0] + ':8080'
    return f'http://{host}/api/v2'


def api(base, path, data=None):
    req = urllib.request.Request(
        base + path, data=urllib.parse.urlencode(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw.strip() else None


def on_disk(t):
    return max(0, t['size'] - t['amount_left'])


def decide(t, now):
    """Reason string to delete this torrent, or None to keep it."""
    if t['amount_left'] > 0 or t['completion_on'] <= 0:
        if (now - t['added_on']) / HRS >= STALE_DL_HOURS:
            return 'stale-incomplete'
        return None
    seeded_h = (now - t['completion_on']) / HRS
    if seeded_h < TRACKER_SAFE_HOURS:
        return None
    if t['state'].startswith(('stopped', 'paused')):
        return 'stopped'
    if (now - t['last_activity']) / HRS >= DEAD_HOURS:
        return 'dead-swarm'
    if seeded_h >= HARD_CAP_HOURS:
        return 'age-cap'
    return None


def cap_victims(kept, now):
    """Extra deletions to get the category under DISK_CAP_GB. Only H&R-safe
    completed torrents qualify; stopped first, then longest-idle."""
    total = sum(on_disk(t) for t in kept)
    cap = DISK_CAP_GB * 2**30
    if total <= cap:
        return [], total
    safe = [t for t in kept
            if t['amount_left'] == 0 and t['completion_on'] > 0
            and (now - t['completion_on']) / HRS >= TRACKER_SAFE_HOURS]
    safe.sort(key=lambda t: (not t['state'].startswith(('stopped', 'paused')),
                             t['last_activity']))
    victims = []
    for t in safe:
        if total <= cap:
            break
        victims.append(t)
        total -= on_disk(t)
    return victims, total


def run(apply):
    now = time.time()
    base = qb_base()
    ts = [t for t in api(base, '/torrents/info') if t['category'] == CATEGORY]
    stamp = time.strftime('%F %T')
    if not ts:
        print(f'{stamp} race category empty, nothing to do')
        return
    doomed = {}
    for t in ts:
        reason = decide(t, now)
        if reason:
            doomed[t['hash']] = (t, reason)
    kept = [t for t in ts if t['hash'] not in doomed]
    victims, projected = cap_victims(kept, now)
    for t in victims:
        doomed[t['hash']] = (t, 'disk-cap')
    for t, reason in doomed.values():
        print(f'{stamp} {"DELETE" if apply else "would-delete"} [{reason}] '
              f'ratio={t["ratio"]:.2f} {on_disk(t) / 2**30:.1f}GiB {t["name"][:70]}')
    if apply and doomed:
        api(base, '/torrents/delete',
            {'hashes': '|'.join(doomed), 'deleteFiles': 'true'})
    left = sum(on_disk(t) for t in ts if t['hash'] not in doomed)
    print(f'{stamp} kept {len(ts) - len(doomed)}, reaped {len(doomed)}, '
          f'category {left / 2**30:.1f}GiB (cap {DISK_CAP_GB}GiB)')
    if projected > DISK_CAP_GB * 2**30:
        print(f'{stamp} WARNING: over disk cap but remaining torrents are '
              f'inside the tracker hit-and-run window; nothing safe to delete')


def selftest():
    now = time.time()
    day = 24 * HRS

    def t(**kw):
        base = dict(hash='x', name='t', category=CATEGORY, state='uploading',
                    size=10 * 2**30, amount_left=0, ratio=1.0,
                    added_on=now - 12 * day, completion_on=now - 11 * day,
                    last_activity=now - 1 * HRS)
        base.update(kw)
        return base

    assert decide(t(completion_on=now - 2 * day, added_on=now - 2 * day), now) is None, 'young keeps'
    assert decide(t(last_activity=now - 4 * day), now) == 'dead-swarm'
    assert decide(t(), now) is None, 'active safe torrent keeps'
    assert decide(t(completion_on=now - 22 * day, added_on=now - 23 * day), now) == 'age-cap'
    assert decide(t(state='stoppedUP'), now) == 'stopped'
    assert decide(t(state='stoppedUP', completion_on=now - 5 * day), now) is None, 'H&R window protects'
    assert decide(t(amount_left=2**30, completion_on=0, added_on=now - 2 * day), now) is None, 'young download keeps'
    assert decide(t(amount_left=2**30, completion_on=0, added_on=now - 8 * day), now) == 'stale-incomplete'

    idle, busy = t(hash='a', last_activity=now - 2 * day, size=300 * 2**30), \
        t(hash='b', size=300 * 2**30)
    victims, total = cap_victims([idle, busy], now)
    assert [v['hash'] for v in victims] == ['a'] and total <= DISK_CAP_GB * 2**30, 'cap prefers idle'
    assert cap_victims([t(size=100 * 2**30)], now) == ([], 100 * 2**30), 'under cap untouched'
    victims, total = cap_victims([t(hash='c', size=600 * 2**30, completion_on=now - 2 * day,
                                    added_on=now - 3 * day)], now)
    assert victims == [] and total > DISK_CAP_GB * 2**30, 'H&R window blocks cap deletes'
    print('selftest OK')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
    else:
        run(apply='--apply' in sys.argv)
