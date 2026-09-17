#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR=/etc/systemd/system

if [[ "$(id -u)" -ne 0 ]]; then
    echo "This script must be run as root (e.g. with sudo)." >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed." >&2
    exit 1
fi

chmod +x "$SCRIPT_DIR/heal.sh" "$SCRIPT_DIR/export_cookies.py"
cp "$SCRIPT_DIR/systemd/igembed-heal.path" "$UNIT_DIR/"
cp "$SCRIPT_DIR/systemd/igembed-heal.service" "$UNIT_DIR/"
systemctl daemon-reload
systemctl enable --now igembed-heal.path

echo "Done. Check with: systemctl status igembed-heal.path"
