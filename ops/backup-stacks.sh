#!/usr/bin/env bash
set -uo pipefail
dest=/mnt/media/backups/$(date +%F); mkdir -p "$dest"
fail=0
failed() { echo "FATAL $*" >&2; fail=$((fail + 1)); }
remote_tar() {
  host=$1 name=$2 command=$3
  runuser -u noah -- ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "$command" > "$dest/$name.tar.gz"
  rc=${PIPESTATUS[0]}
  if [ "$rc" -ge 2 ]; then failed "$host tar rc=$rc for $name"; fi
}

for d in /home/noah/docker/qbittorrentvpn/config /home/noah/docker/qbittorrentvpn/jfa-go \
         /home/noah/docker/jellyfin/config /opt/donetick /opt/homeassist /opt/pihole \
         /home/noah/milkhaus-site /home/noah/docker/roundcube /home/noah/.config/bot-autodeploy; do
  out="$dest/$(basename "$(dirname "$d")")-$(basename "$d").tar.gz"
  tar -C "$(dirname "$d")" --exclude=config/temp --exclude=config/metadata --exclude=config/data/trickplay \
      --exclude=pihole/etc-pihole/gravity.db -czf "$out" "$(basename "$d")"; rc=$?
  if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for $d"; fi
done
find /home/noah/docker -type f \( -name docker-compose.yml -o -name '*.env' -o -name .env \) \
  -printf 'home/noah/docker/%P\0' | tar --null -C / -T - -czf "$dest/noahlab-docker-compose-env.tar.gz"; rc=${PIPESTATUS[1]}
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for docker compose/env files"; fi
tar -C /home/noah/docker/jellyfin -czf "$dest/noahlab-jellyfin-extra.tar.gz" cloudflared web; rc=$?
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for jellyfin cloudflared/web"; fi
tar -C /home/noah --exclude='discordbot/.git' --exclude='discordbot/*/.git' \
  --exclude='discordbot/*/node_modules' --exclude='discordbot/*/.venv' --exclude='discordbot/*/venv' \
  --exclude='discordbot/*/__pycache__' --exclude='discordbot/*/old-banners' \
  --exclude='discordbot/TETO-BOT-EVERYTHING' -czf "$dest/noahlab-discordbot.tar.gz" discordbot; rc=$?
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for /home/noah/discordbot"; fi
tar -C /home/noah -czf "$dest/noahlab-user-config.tar.gz" .config/teto .config/audible .config/systemd/user; rc=$?
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for noah user config"; fi
tar -C /home/noah --exclude='pzstats/gamedata' --exclude='pzstats/__pycache__' \
  -czf "$dest/noahlab-tools.tar.gz" bin pzstats mcstats; rc=$?
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for noah tools"; fi
tar -C /home/noah --exclude='homelab/.git' --exclude='homelab/*/__pycache__' \
  -czf "$dest/noahlab-homelab.tar.gz" homelab; rc=$?
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for /home/noah/homelab"; fi
hype_data=$(docker volume inspect -f '{{.Mountpoint}}' goodnod_hype-data 2>/dev/null); rc=$?
if [ "$rc" -eq 0 ] && [ -n "$hype_data" ]; then
  tar -C "$(dirname "$hype_data")" -czf "$dest/noahlab-goodnod-hype-data.tar.gz" "$(basename "$hype_data")"; rc=$?
  if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for goodnod_hype-data"; fi
else failed "docker volume inspect rc=$rc for goodnod_hype-data"; fi
tar -C / -czf "$dest/noahlab-pterodactyl-config.tar.gz" opt/pterodactyl/themes etc/pterodactyl/config.yml; rc=$?
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for pterodactyl themes/wings config"; fi
tar -C /var/lib/pterodactyl/volumes -czf "$dest/noahlab-factorio-volumes.tar.gz" \
  224908c7-1565-4a0c-8249-d4fc2b834f86 c6e63d7d-0d5e-4a85-862a-ce956c6dc2b7; rc=$?
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for Factorio volumes"; fi
find /etc/systemd/system -maxdepth 1 \( -name '*.service' -o -name '*.timer' \) \
  -printf 'etc/systemd/system/%f\0' | tar --null -C / -T - \
  etc/systemd/system/getty@tty1.service.d usr/local/bin usr/local/etc \
  -czf "$dest/noahlab-host-config.tar.gz"; rc=${PIPESTATUS[1]}
if [ "$rc" -ge 2 ]; then failed "tar rc=$rc for noahlab host config"; fi
crontab -l -u root > "$dest/noahlab-root-crontab.txt"; rc=$?
if [ "$rc" -ne 0 ]; then failed "crontab rc=$rc for root"; fi
crontab -l -u noah > "$dest/noahlab-noah-crontab.txt"; rc=$?
if [ "$rc" -ne 0 ]; then failed "crontab rc=$rc for noah"; fi

runuser -u noah -- ssh -o BatchMode=yes -o ConnectTimeout=10 jesus \
  "sudo -n docker compose -f /opt/pterodactyl/docker-compose.yml exec -T database sh -c 'exec mysqldump --all-databases -uroot -p\"\$MYSQL_ROOT_PASSWORD\"'" \
  | gzip > "$dest/jesus-pterodactyl-db.sql.gz"
ssh_rc=${PIPESTATUS[0]} gzip_rc=${PIPESTATUS[1]}
if [ "$ssh_rc" -ne 0 ]; then failed "jesus mysqldump rc=$ssh_rc"; fi
if [ "$gzip_rc" -ne 0 ]; then failed "gzip rc=$gzip_rc for jesus mysqldump"; fi
remote_tar jesus jesus-pterodactyl "sudo -n tar czf - -C /opt --exclude=pterodactyl/db --exclude=pterodactyl/logs pterodactyl -C /etc pterodactyl/config.yml"
remote_tar jesus jesus-frigate "sudo -n tar czf - -C /opt --exclude=frigate/storage --exclude=frigate/config/model_cache frigate"
remote_tar jesus jesus-grafana-monitoring "sudo -n tar czf - -C /opt grafana monitoring"
remote_tar jesus jesus-prometheus "sudo -n tar czf - -C /opt --exclude=prometheus/data prometheus"
remote_tar jesus jesus-audible "sudo -n tar czf - -C /home/noah --exclude=fantasy-football-assistant/node_modules --exclude=fantasy-football-assistant/.venv --exclude=fantasy-football-assistant/venv --exclude=fantasy-football-assistant/__pycache__ --exclude=fantasy-football-assistant/.pytest_cache --exclude=fantasy-football-assistant/data/artifacts/.profiles fantasy-football-assistant"
remote_tar jesus jesus-lair "sudo -n tar czf - -C /home/noah --exclude=lair/__pycache__ lair"
remote_tar jesus jesus-westly "sudo -n tar czf - -C /home/noah westly"
remote_tar jesus jesus-host-files "sudo -n tar czf - -C / home/noah/bin usr/local/etc"
runuser -u noah -- ssh -o BatchMode=yes -o ConnectTimeout=10 jesus 'crontab -l' > "$dest/jesus-noah-crontab.txt"; rc=$?
if [ "$rc" -ne 0 ]; then failed "jesus crontab rc=$rc for noah"; fi
remote_tar jesus jesus-zomboid "sudo -n tar czf - -C /var/lib/pterodactyl/volumes/16701806-de59-4dc1-b913-cf5022fbab7d --exclude=.cache/Logs --exclude=.cache/server-console.txt .cache"

minecraft_rcon() {
  python3 - "$1" <<'PY'
import socket, struct, sys
props = {}
with open('/var/lib/pterodactyl/volumes/8c5d7972-61bc-4e9a-bc2a-fcb1e7448051/server.properties') as f:
    for line in f:
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.rstrip('\n').split('=', 1); props[key] = value
password = props.get('rcon.password'); port = int(props.get('rcon.port', '25575'))
if not password: raise SystemExit(1)
def pack(rid, kind, body):
    payload = struct.pack('<ii', rid, kind) + body.encode() + b'\0\0'
    return struct.pack('<i', len(payload)) + payload
def read(sock):
    head = b''
    while len(head) < 4:
        chunk = sock.recv(4 - len(head))
        if not chunk: raise OSError('closed')
        head += chunk
    length, = struct.unpack('<i', head); data = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk: raise OSError('closed')
        data += chunk
    return struct.unpack('<i', data[:4])[0]
try:
    with socket.create_connection(('192.168.1.212', port), timeout=5) as sock:
        sock.sendall(pack(1, 3, password))
        if read(sock) == -1: raise OSError('authentication failed')
        sock.sendall(pack(2, 2, sys.argv[1])); read(sock)
except (OSError, ValueError): raise SystemExit(1)
PY
}
minecraft_saving_off=0
minecraft_save_on() {
  if [ "$minecraft_saving_off" -ne 0 ]; then
    if ! minecraft_rcon save-on; then echo "WARNING Minecraft RCON save-on failed" >&2; fi
    minecraft_saving_off=0
  fi
}
trap minecraft_save_on EXIT
if minecraft_rcon save-off; then
  minecraft_saving_off=1
  if ! minecraft_rcon 'save-all flush'; then echo "WARNING Minecraft RCON save-all flush failed; continuing backup" >&2; fi
else echo "WARNING Minecraft RCON save-off failed; continuing backup" >&2; fi
remote_tar pablo pablo-minecraft "sudo -n tar czf - -C /var/lib/pterodactyl/volumes/8c5d7972-61bc-4e9a-bc2a-fcb1e7448051 --anchored --exclude=./bluemap --exclude=./cache --exclude=./libraries --exclude=./versions --exclude=./logs --exclude=./server.jar --exclude=./server.jar.old --exclude=./_world_26.2_orphan ."
minecraft_save_on
remote_tar pablo pablo-tacticus "sudo -n tar czf - -C /home/noah --exclude=tacticus-bot/__pycache__ --exclude='tacticus-bot/*.png' tacticus-bot tacticus.md"
remote_tar pablo pablo-pterodactyl "sudo -n tar czf - -C / etc/pterodactyl/config.yml"
remote_tar root@vps.example.net vps-edge-config "tar czf - -C / etc/caddy etc/wireguard etc/iptables etc/ufw"
runuser -u noah -- ssh -o BatchMode=yes -o ConnectTimeout=10 root@vps.example.net 'crontab -l' > "$dest/vps-root-crontab.txt"; rc=$?
if [ "$rc" -ne 0 ]; then failed "VPS crontab rc=$rc for root"; fi

ls -dt /mnt/media/backups/*/ | tail -n +15 | xargs -r rm -rf

# mirror to the dedicated backup disk; a missing mount must scream, not skip
if mountpoint -q /mnt/backup; then
  rsync -a --delete /mnt/media/backups/ /mnt/backup/backups/ || { rc=$?; echo "FATAL mirror rsync rc=$rc" >&2; fail=$((fail + 1)); }
else
  echo "FATAL mirror target /mnt/backup not mounted" >&2; fail=$((fail + 1))
fi
if [ "$fail" -ne 0 ]; then
  runuser -u noah -- /usr/local/bin/fleet-alert "backup-stacks on noahlab: $fail step(s) failed, see ~/.backup-stacks.log"
fi
exit $fail
