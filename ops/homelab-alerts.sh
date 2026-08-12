#!/usr/bin/env bash
# Homelab health checks -> one push to Noah's phone via vd-flag.
# State file holds "<key> <epoch-of-last-alert>"; a persisting condition re-alerts every 24h.
set -uo pipefail
case "${1:-}" in --dry-run) dry=1;; "") dry=0;; *) echo "usage: $0 [--dry-run]" >&2; exit 2;; esac
state=/home/noah/.homelab-alerts.state
now=$(date +%s)
declare -A fire

pct=$(df -P /mnt/media 2>/dev/null | awk 'NR==2{print $5+0}'); pct=${pct:-0}
[ "$pct" -ge "${ALERT_DISK_PCT:-85}" ] && fire[disk]="media disk ${pct}% full"

newest=$(find /mnt/media/backups -mindepth 1 -maxdepth 1 -type d -name '????-??-??' -printf '%Ts\n' 2>/dev/null | sort -n | tail -1)
if [ -z "$newest" ]; then fire[backup-age]="no dated backup dirs under /mnt/media/backups"
elif [ $(( (now - newest) / 3600 )) -ge "${ALERT_BACKUP_HOURS:-26}" ]; then fire[backup-age]="newest backup is $(( (now - newest) / 3600 ))h old"
fi

down=$(docker inspect --format '{{.Name}} {{.HostConfig.RestartPolicy.Name}} {{.State.Status}}' $(docker ps -aq) 2>/dev/null \
  | awk '($2=="always"||$2=="unless-stopped")&&($3=="exited"||$3=="dead"){sub(/^\//,"",$1);printf "%s%s",s,$1;s=","}')
[ -n "$down" ] && fire[dead-containers]="containers down: $down"

mountpoint -q /mnt/backup || fire[mirror]="backup mirror /mnt/backup not mounted"

send=""; new=""
for k in disk backup-age dead-containers mirror; do
  m=${fire[$k]:-}
  if [ -z "$m" ]; then [ "$dry" = 1 ] && echo "ok      $k"; continue; fi
  last=$(awk -v k="$k" '$1==k&&$2~/^[0-9]+$/{print $2}' "$state" 2>/dev/null)
  if [ -z "$last" ] || [ $(( now - last )) -ge 86400 ]; then
    send+="${send:+; }$m"; new+="$k $now"$'\n'
    [ "$dry" = 1 ] && echo "FIRING  $k: $m -> would alert"
  else
    new+="$k $last"$'\n'
    [ "$dry" = 1 ] && echo "FIRING  $k: $m -> suppressed, last alert $(( (now - last) / 3600 ))h ago"
  fi
done

if [ "$dry" = 1 ]; then
  [ -n "$send" ] && echo "would send: homelab: $send" || echo "would send: nothing"
  exit 0
fi
printf '%s' "$new" > "$state.tmp" && mv -f "$state.tmp" "$state"
[ -n "$send" ] && { /home/noah/bin/vd-flag "homelab: $send" || echo "homelab-alerts: vd-flag failed" >&2; }
exit 0
