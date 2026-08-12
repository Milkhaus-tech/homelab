#!/usr/bin/env bash
set -euo pipefail

MAX_TEMP=82
COOLDOWN_TEMP=70
THREADS=6
HWMON_PATH="/sys/class/hwmon/hwmon0/temp1_input"
LOG_FILE="/opt/xmrig/logs/xmrig.log"
HUGEPAGES=256

log() {
  echo "[$(date --iso-8601=seconds)] $*" | tee -a "$LOG_FILE"
}

ensure_prereqs() {
  # Hugepages setup
  sysctl -w "vm.nr_hugepages=${HUGEPAGES}" >/dev/null 2>&1 || true

  # Load MSR module (wrapper runs as root; no permission change needed)
  if ! lsmod | grep -q "^msr"; then
    modprobe msr || log "WARN: failed to load msr module"
  fi
}

current_temp() {
  if [[ -r "$HWMON_PATH" ]]; then
    awk '{printf "%.0f\n", $1/1000}' "$HWMON_PATH"
  else
    echo 0
  fi
}

cooldown_loop() {
  while true; do
    sleep 5
    local t
    t=$(current_temp)
    if (( t <= COOLDOWN_TEMP )); then
      log "Cooldown complete: ${t}°C <= ${COOLDOWN_TEMP}°C"
      return 0
    fi
    log "Cooling down: ${t}°C > ${COOLDOWN_TEMP}°C"
  done
}

monitor_temp() {
  while true; do
    sleep 5
    local t
    t=$(current_temp)
    if (( t > MAX_TEMP )); then
      log "OVERHEAT: ${t}°C > ${MAX_TEMP}°C — killing miner"
      pkill -TERM xmrig || true
      return 1
    fi
  done
}

main() {
  ensure_prereqs

  local t
  t=$(current_temp)
  if (( t > MAX_TEMP )); then
    log "ABORT: CPU temp ${t}°C > ${MAX_TEMP}°C"
    exit 1
  fi

  log "Starting XMRig (temp=${t}°C hugepages=${HUGEPAGES} threads=${THREADS})"

  /opt/xmrig/build/xmrig     --config=/opt/xmrig/config.json     --threads=$THREADS     --cpu-max-threads-hint=100     --cpu-priority=5     --huge-pages     --syslog     2>&1 | tee -a "$LOG_FILE" &
  miner_pid=$!

  monitor_temp &
  mon_pid=$!

  # Unwind when EITHER exits: miner death (crash/OOM/kill) or watchdog overheat trip
  rc=0
  wait -n || rc=$?

  kill "$miner_pid" "$mon_pid" 2>/dev/null || true
  pkill -TERM xmrig 2>/dev/null || true

  if (( $(current_temp) > COOLDOWN_TEMP )); then
    log "Entering cooldown before restart"
    cooldown_loop
  fi

  log "Exiting wrapper (rc=${rc}) so systemd restarts miner"
  exit 1
}

main "$@"
