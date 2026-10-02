#!/usr/bin/env bash
# verify-no-leaks.sh — refuse to let a credential into the publish tree.
#
# Net 1 (always): pattern sweep over every file git would publish — JWTs, private
#   key blocks, inline rtsp credentials, webhook ids, and value-bearing
#   password/secret/token/api-key assignments that aren't an approved placeholder.
# Net 2 (on the lab box only, skipped by --patterns-only): harvest the *actual*
#   secret values from the live secret stores and prove none of them appear
#   anywhere in the tree. Values are never printed — hits report the source
#   label (file:key) and the offending repo file only.
#
# Exit nonzero on any hit. CI runs --patterns-only; sync-from-live.sh runs both.
set -uo pipefail
cd "$(dirname "$0")/.."
mode="${1:-full}"
fail=0

files=$(git ls-files -c -o --exclude-standard | grep -v '^tools/.private-tokens$')

## ---- net 1: credential-shaped patterns ----
pat='eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|BEGIN [A-Z ]*PRIVATE KEY|rtsp://[^{<$@/[:space:]]+:[^{<$@/[:space:]]+@|api/webhook/[a-f0-9]{16,}|(password|passwd|secret|token|api_?key|apikey|private_?key|access_?key)["'"'"'[:space:]]*[:=]["'"'"'[:space:]]*[A-Za-z0-9+/][A-Za-z0-9+/._!^-]{9,}'
allow='\$\{[A-Za-z_]+\}|\{FRIGATE_[A-Z_]+\}|!secret |<redacted>|<your-|changeme|your_[a-z_]+|_here\b|example|REDACTED|- /[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+:|(token|secret|password)["'"'"'[:space:]]*[:=][[:space:]]*[A-Za-z_][A-Za-z0-9_.]*\('
hits=$(echo "$files" | xargs -r grep -nEIiH "$pat" 2>/dev/null | grep -vE "$allow" || true)
if [ -n "$hits" ]; then
  echo "PATTERN HITS (value-bearing lines in the publish tree):" >&2
  echo "$hits" | cut -c1-160 >&2
  fail=1
fi

[ "$mode" = "--patterns-only" ] && exit $fail

## ---- net 2: live secret values must appear nowhere ----
export VERIFY_FILES="$files"
python3 - <<'PY' || fail=1
import json, os, re, subprocess, sys, urllib.parse

def read(path):
    try:
        return open(path, errors="replace").read()
    except (PermissionError, FileNotFoundError):
        r = subprocess.run(["sudo", "-n", "cat", path], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""

pairs = []          # (label, value) — label printed on a hit, value never
def add(label, val):
    val = (val or "").strip().strip("'\"")
    if len(val) >= 6 and not val.startswith("$") and "{" not in val:
        pairs.append((label, val))

# .env-style files: every value is a secret here
for envf in ["/home/noah/docker/qbittorrentvpn/.env", "/opt/monitoring/.env",
             "/opt/donetick/.env"]:
    for line in read(envf).splitlines():
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.+)$", line)
        if m and not line.lstrip().startswith("#"):
            add(f"{envf}:{m.group(1)}", m.group(2))

# mixed-content stores: only secret-named keys (host/user/url keys are not secrets)
secretkey = re.compile(r"^\s*([A-Za-z0-9_-]*(pass|password|secret|token|apikey|api_key|_key|salt)[A-Za-z0-9_-]*)\s*[:=]\s*(.+)$", re.I)
for f in ["/opt/homeassist/config/secrets.yaml", "/etc/pterodactyl/config.yml",
          "/opt/pterodactyl/var/.env",
          "/home/noah/docker/qbittorrentvpn/config/autobrr/config.toml",
          "/home/noah/docker/qbittorrentvpn/config/recyclarr/secrets.yml"]:
    for line in read(f).splitlines():
        m = secretkey.match(line)
        # Home Assistant ships "some_password: welcome" as its example secret
        if m and (m.group(1), m.group(3).strip()) != ("some_password", "welcome"):
            add(f"{f}:{m.group(1)}", m.group(3))

# mosquitto password hashes
for line in read("/opt/homeassist/mosquitto/config/passwd").splitlines():
    if ":" in line:
        add("mosquitto:passwd-hash", line.split(":", 1)[1])

# xmrig wallet (pool "pass" is skipped when it's just the worker/hostname tag)
import socket
try:
    for p in json.loads(read("/opt/xmrig/config.json") or "{}").get("pools", []):
        add("xmrig:wallet", p.get("user", ""))
        if (p.get("pass") or "").split(":")[0] != socket.gethostname():
            add("xmrig:pass", p.get("pass", ""))
except json.JSONDecodeError:
    pass

# inline secrets in live files that sync-from-live.sh templates out
fc = read("/opt/frigate/config/config.yaml")
for u, pw in re.findall(r"rtsp://([^:/@\s]+):([^@\s]+)@", fc):
    add("frigate:camera-user", u); add("frigate:camera-pass", pw)
for pw in re.findall(r"^\s*password:\s*(.+)$", fc, re.M):
    add("frigate:password", pw)
add("frigate:rtsp-pass", "".join(re.findall(r"FRIGATE_RTSP_PASSWORD=(\S+)", read("/opt/frigate/docker-compose.yml"))))
add("ha:matter-token", "".join(re.findall(r"TOKEN=(\S+)", read("/opt/homeassist/docker-compose.yml"))))
for wid in re.findall(r"webhook_id:\s*([a-f0-9]{16,})", read("/opt/homeassist/config/automations.yaml")):
    add("ha:webhook-id", wid)
for k, v in re.findall(r"(MYSQL_PASSWORD|MYSQL_ROOT_PASSWORD):\s*\"?([^\"\n]+)", read("/opt/pterodactyl/docker-compose.yml")):
    add(f"pterodactyl:{k}", v)
add("vd-desktop:sunshine-pass", "".join(re.findall(r"VD_SUNSHINE_PASS:-([^}]+)\}", read("/home/noah/bin/vd-desktop"))))
add("vd-flag:webhook", "".join(re.findall(r"api/webhook/([a-f0-9]+)", read("/home/noah/bin/vd-flag"))))

# identity/topology strings that must stay out of the public tree
add("identity:email-localpart", subprocess.run(["git", "config", "user.email"],
    capture_output=True, text=True).stdout.split("@")[0])
add("identity:vps-ip", "".join(re.findall(r"\d+\.\d+\.\d+\.\d+", read("/home/noah/milkhaus-site/deploy.sh"))[:1]))
try:
    ts = json.loads(subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True).stdout)
    add("tailnet:suffix", ts.get("MagicDNSSuffix", ""))
    for node in [ts.get("Self", {})] + list(ts.get("Peer", {}).values()):
        for ip in node.get("TailscaleIPs", []):
            if ip.startswith("100."):
                add("tailnet:ip", ip)
except Exception:
    print("WARN: tailscale status unavailable; tailnet addresses unchecked", file=sys.stderr)

# private rename tokens: the old names must not survive
for line in read("tools/.private-tokens").splitlines():
    if "=" in line:
        add("private-token", line.split("=", 1)[0])

# scan every publishable file for every value (raw + URL-encoded forms)
targets = [f for f in os.environ["VERIFY_FILES"].splitlines() if f and os.path.isfile(f)]
bad = 0
for path in targets:
    blob = open(path, errors="replace").read()
    for label, val in pairs:
        forms = {val, urllib.parse.quote(val), urllib.parse.quote(val, safe="")}
        if any(f in blob for f in forms if f):
            print(f"VALUE HIT: {label} found in {path}", file=sys.stderr)
            bad = 1
if not pairs:
    print("WARN: harvested zero live secrets — wrong box?", file=sys.stderr); sys.exit(1)
print(f"value sweep: {len(pairs)} live secrets checked against {len(targets)} files")
sys.exit(bad)
PY

exit $fail
