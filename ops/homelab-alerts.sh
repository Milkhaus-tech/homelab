#!/usr/bin/env bash
# Homelab health checks -> one push to Noah's phone via vd-flag.
# State file holds "<key> <epoch-of-last-alert>"; a persisting condition re-alerts every 24h.
set -uo pipefail
case "${1:-}" in --dry-run) dry=1;; "") dry=0;; *) echo "usage: $0 [--dry-run]" >&2; exit 2;; esac
state=/home/noah/.homelab-alerts.state
now=$(date +%s)
declare -A fire

pct=$(df -P /mnt/media 2>/dev/null | awk 'NR==2{print $5+0}'); pct=${pct:-0}
# disk alerts by band: a new higher band alerts at once; 85-94% repeats weekly, 95%+ daily
# (it re-alerted at 85-89% every day for 8 weeks, which taught everyone to ignore it)
band=0; for b in "${ALERT_DISK_PCT:-85}" 90 95; do [ "$pct" -ge "$b" ] && band=$b; done
[ "$band" -gt 0 ] && fire[disk]="media disk ${pct}% full"

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
  read -r last lastsig <<<"$(awk -v k="$k" '$1==k&&$2~/^[0-9]+$/{print $2, $3}' "$state" 2>/dev/null)"
  # dead-containers re-alerts on a changed set, not just every 24h — a standing
  # alert must never mask a newly dead container (masked mcstats on 2026-08-19)
  sig=""; every=86400; changed=0
  [ "$k" = dead-containers ] && sig=$down && [ "$sig" != "$lastsig" ] && changed=1
  if [ "$k" = disk ]; then
    sig=$band; [ "$band" -lt 95 ] && every=604800
    [ "$band" -gt "${lastsig:-${ALERT_DISK_PCT:-85}}" ] && changed=1
  fi
  if [ -z "$last" ] || [ $(( now - last )) -ge "$every" ] || [ "$changed" = 1 ]; then
    send+="${send:+; }$m"; new+="$k $now${sig:+ $sig}"$'\n'
    [ "$dry" = 1 ] && echo "FIRING  $k: $m -> would alert"
  else
    new+="$k $last${lastsig:+ $lastsig}"$'\n'
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
