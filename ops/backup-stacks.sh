#!/usr/bin/env bash
set -uo pipefail
dest=/mnt/media/backups/$(date +%F); mkdir -p "$dest"
fail=0
for d in /home/noah/docker/qbittorrentvpn/config /home/noah/docker/qbittorrentvpn/jfa-go \
         /home/noah/docker/jellyfin/config /home/noah/docker/tdarr/server /home/noah/docker/tdarr/configs \
         /opt/donetick /opt/frigate /opt/homeassist /opt/monitoring /opt/grafana; do
  out="$dest/$(basename "$(dirname "$d")")-$(basename "$d").tar.gz"
  # rc=1 (file changed mid-read) is expected on live dbs; temp is scratch, metadata/trickplay regenerable,
  # frigate/storage is stale pre-migration footage
  tar -C "$(dirname "$d")" --exclude=config/temp --exclude=config/metadata --exclude=config/data/trickplay \
      --exclude=frigate/storage -czf "$out" "$(basename "$d")"; rc=$?
  if [ "$rc" -ge 2 ]; then echo "FATAL tar rc=$rc for $d" >&2; fail=1; fi
done
# prometheus: config + ha_token only; data/ is the TSDB, metrics history not worth keeping
tar -czf "$dest/opt-prometheus.tar.gz" -C /opt --exclude=prometheus/data prometheus; rc=$?
if [ "$rc" -ge 2 ]; then echo "FATAL tar rc=$rc for /opt/prometheus" >&2; fail=1; fi
# pterodactyl: DB dump + panel/wings config; world saves are in-panel scheduled backups
docker compose -f /opt/pterodactyl/docker-compose.yml exec -T database \
  sh -c 'exec mysqldump --all-databases -uroot -p"$MYSQL_ROOT_PASSWORD"' | gzip > "$dest/pterodactyl-db.sql.gz"
rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then echo "FATAL mysqldump rc=$rc" >&2; fail=1; fi
tar -czf "$dest/pterodactyl-config.tar.gz" -C /opt/pterodactyl var docker-compose.yml -C /etc pterodactyl/config.yml; rc=$?
if [ "$rc" -ge 2 ]; then echo "FATAL tar rc=$rc for pterodactyl config" >&2; fail=1; fi

ls -dt /mnt/media/backups/*/ | tail -n +15 | xargs -r rm -rf

# mirror to the dedicated backup disk; a missing mount must scream, not skip
if mountpoint -q /mnt/backup; then
  rsync -a --delete /mnt/media/backups/ /mnt/backup/backups/ || { echo "FATAL mirror rsync rc=$?" >&2; fail=1; }
else
  echo "FATAL mirror target /mnt/backup not mounted" >&2; fail=1
fi
exit $fail
