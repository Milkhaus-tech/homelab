#!/usr/bin/env bash
# sync-from-live.sh — export live configs into this repo with secrets templated out.
#
# This repo is a sanitized mirror. The deployment source of truth is the live tree
# (/opt/*, ~/docker/*, ~/bin, /etc/systemd/system); this script re-exports every
# published file from it, applies the redaction rules below, then runs
# tools/verify-no-leaks.sh and fails loudly if anything credential-shaped survives.
#
# Redaction rules are patterns, never literal secret values, so this script is safe
# to publish. Substitutions that would themselves reveal a private string (e.g.
# renaming a person) are read from tools/.private-tokens (untracked, `old=new` lines).
set -euo pipefail
cd "$(dirname "$0")/.."
H=/home/noah

# X <mode> <src> <dst> [sed-script...] — copy, chmod, then apply each sed -E in place.
X() {
  local mode=$1 src=$2 dst=$3; shift 3
  [ -r "$src" ] || { echo "MISSING: $src" >&2; exit 1; }
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"; chmod "$mode" "$dst"
  local s; for s in "$@"; do sed -Ei "$s" "$dst"; done
}

# priv <file> — apply the untracked old=new rename map, if present.
priv() {
  [ -f tools/.private-tokens ] || return 0
  local k v
  while IFS='=' read -r k v; do
    [ -n "$k" ] && sed -i "s/${k}/${v}/g" "$1"
  done < tools/.private-tokens
}

## ---- media pipeline (already ${VAR}-templated in live) ----
X 644 "$H/docker/qbittorrentvpn/docker-compose.yml"                        services/media/docker-compose.yml
X 644 "$H/docker/qbittorrentvpn/config/recyclarr/configs/recyclarr.yml"    services/media/recyclarr/recyclarr.yml
X 755 "$H/bin/race-reaper.py"                                              services/media/scripts/race-reaper.py
priv services/media/scripts/race-reaper.py
X 755 "$H/bin/media-dedup.py"                                              services/media/scripts/media-dedup.py

## ---- jellyfin ----
X 644 "$H/docker/jellyfin/docker-compose.yml"                              services/jellyfin/docker-compose.yml
X 755 "$H/bin/livetv-curate.py"                                            services/jellyfin/scripts/livetv-curate.py

## ---- frigate ----
X 644 /opt/frigate/docker-compose.yml services/frigate/docker-compose.yml \
  's/FRIGATE_RTSP_PASSWORD=.*/FRIGATE_RTSP_PASSWORD=${FRIGATE_RTSP_PASSWORD}/' \
  's/^(\s*)(- FRIGATE_RTSP_PASSWORD=.*)/\1\2\n\1- FRIGATE_CAMERA_USER=${FRIGATE_CAMERA_USER}\n\1- FRIGATE_CAMERA_PASSWORD=${FRIGATE_CAMERA_PASSWORD}\n\1- FRIGATE_MQTT_PASSWORD=${FRIGATE_MQTT_PASSWORD}/'
# config.yaml needs block-aware handling: camera creds vs the (non-secret) mqtt username.
python3 - <<'PY'
import re
out, top = [], ""
for line in open("/opt/frigate/config/config.yaml"):
    if line.strip() and not line.startswith((" ", "\t")):
        top = line.split(":")[0].strip()
    line = re.sub(r"rtsp://[^:/@\s]+:[^@\s]+@", "rtsp://{FRIGATE_CAMERA_USER}:{FRIGATE_CAMERA_PASSWORD}@", line)
    if top != "mqtt":
        line = re.sub(r"^(\s*user:).*$", r"\1 '{FRIGATE_CAMERA_USER}'", line)
    line = re.sub(r"^(\s*password:).*$",
                  r"\1 '{FRIGATE_MQTT_PASSWORD}'" if top == "mqtt" else r"\1 '{FRIGATE_CAMERA_PASSWORD}'",
                  line)
    out.append(line)
open("services/frigate/config.yaml", "w").writelines(out)
PY

## ---- home assistant + mosquitto ----
X 644 /opt/homeassist/docker-compose.yml services/home-assistant/docker-compose.yml \
  's#TOKEN=[A-Za-z0-9._-]+#TOKEN=${HA_MATTER_TOKEN}#'
X 644 /opt/homeassist/config/configuration.yaml   services/home-assistant/configuration.yaml
X 644 /opt/homeassist/config/automations.yaml     services/home-assistant/automations.yaml \
  's/(webhook_id:) .*/\1 <redacted>/'
priv services/home-assistant/automations.yaml
X 644 /opt/homeassist/config/scripts.yaml         services/home-assistant/scripts.yaml
X 644 /opt/homeassist/mosquitto/config/mosquitto.conf services/home-assistant/mosquitto.conf

## ---- monitoring ----
X 644 /opt/monitoring/docker-compose.yml          services/monitoring/docker-compose.yml
X 644 /opt/prometheus/prometheus.yml              services/monitoring/prometheus.yml
X 644 /opt/monitoring/dashboards/build_glance.py   services/monitoring/dashboards/build_glance.py
X 644 /opt/monitoring/dashboards/build_overview.py services/monitoring/dashboards/build_overview.py

## ---- pterodactyl (panel compose carries DB creds inline in live) ----
X 644 /opt/pterodactyl/docker-compose.yml services/pterodactyl/docker-compose.yml \
  's/MYSQL_PASSWORD: .*/MYSQL_PASSWORD: "${MYSQL_PASSWORD}"/' \
  's/MYSQL_ROOT_PASSWORD: .*/MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASSWORD}"/' \
  's/DB_PASSWORD: .*/DB_PASSWORD: "${MYSQL_PASSWORD}"/' \
  's/MAIL_USERNAME: .*/MAIL_USERNAME: "${MAIL_USERNAME}"/' \
  's/MAIL_FROM: .*/MAIL_FROM: "${MAIL_USERNAME}"/' \
  's/MAIL_FROM_ADDRESS: .*/MAIL_FROM_ADDRESS: "${MAIL_USERNAME}"/'
X 755 /usr/local/bin/ptero-net-watchdog                          services/pterodactyl/ptero-net-watchdog
X 644 /etc/systemd/system/ptero-net-watchdog.service             services/pterodactyl/systemd/ptero-net-watchdog.service
X 644 /etc/systemd/system/ptero-net-watchdog.timer               services/pterodactyl/systemd/ptero-net-watchdog.timer
X 755 /usr/local/bin/factorio-autoupdate                         services/pterodactyl/factorio-autoupdate
X 644 /etc/systemd/system/factorio-autoupdate.service            services/pterodactyl/systemd/factorio-autoupdate.service
X 644 /etc/systemd/system/factorio-autoupdate.timer              services/pterodactyl/systemd/factorio-autoupdate.timer

## ---- pzstats ----
X 644 "$H/pzstats/docker-compose.yml"             services/pzstats/docker-compose.yml
X 755 "$H/pzstats/generate.py"                    services/pzstats/generate.py
X 644 "$H/pzstats/www/index.html"                 services/pzstats/www/index.html
X 644 /etc/systemd/system/pzstats.service         services/pzstats/systemd/pzstats.service
X 644 /etc/systemd/system/pzstats.timer           services/pzstats/systemd/pzstats.timer

## ---- donetick ----
X 644 /opt/donetick/docker-compose.yml            services/donetick/docker-compose.yml

## ---- xmrig ----
X 755 /opt/xmrig/run-safe-xmrig.sh                services/xmrig/run-safe-xmrig.sh
X 644 /etc/systemd/system/xmrig.service           services/xmrig/xmrig.service

## ---- host ops ----
X 755 "$H/bin/backup-stacks.sh"                   ops/backup-stacks.sh
X 755 "$H/bin/homelab-alerts.sh"                  ops/homelab-alerts.sh
X 755 "$H/portwatch.sh"                           ops/portwatch.sh
X 755 "$H/portwatch-tally.sh"                     ops/portwatch-tally.sh

## ---- edge ----
X 644 "$H/milkhaus-site/vps/Caddyfile"            edge/Caddyfile

## ---- virtual desktop ----
X 644 /etc/X11/xorg.conf                          virtual-desktop/xorg.conf
X 644 "$H/.xinitrc"                               virtual-desktop/xinitrc
X 755 "$H/bin/vd-browser"                         virtual-desktop/bin/vd-browser
X 755 "$H/bin/vd-input-bridge"                    virtual-desktop/bin/vd-input-bridge
X 755 "$H/bin/vd-pair-sync"                       virtual-desktop/bin/vd-pair-sync
X 755 "$H/bin/audible-desktops"                   virtual-desktop/bin/audible-desktops
X 755 "$H/bin/audible-warroom"                    virtual-desktop/bin/audible-warroom
X 755 "$H/bin/vd-desktop" virtual-desktop/bin/vd-desktop \
  's/VD_SUNSHINE_USER:-[^}]*/VD_SUNSHINE_USER:-moonlight/' \
  's/VD_SUNSHINE_PASS:-[^}]*/VD_SUNSHINE_PASS:-changeme/' \
  's#https://100\.[0-9]+\.[0-9]+\.[0-9]+:#https://<tailscale-ip>:#'
X 755 "$H/bin/vd-flag" virtual-desktop/bin/vd-flag \
  's#(api/webhook/)[a-f0-9]+#\1<your-webhook-id>#'
X 644 /etc/systemd/system/getty@tty1.service.d/override.conf  virtual-desktop/systemd/getty-autologin-override.conf
X 644 "$H/.config/systemd/user/sunshine.service"              virtual-desktop/systemd/sunshine.service
X 644 "$H/.config/systemd/user/audible-agent@.service"        virtual-desktop/systemd/audible-agent@.service
X 644 "$H/.config/systemd/user/audible-warroom.service"       virtual-desktop/systemd/audible-warroom.service
X 644 "$H/.config/systemd/user/audible-warroom.timer"         virtual-desktop/systemd/audible-warroom.timer

echo "sync: files exported, running leak verification..."
./tools/verify-no-leaks.sh
echo "sync: OK — tree is clean"
