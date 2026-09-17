#!/usr/bin/env bash
set -euo pipefail

BOT_DATA="${BOT_DATA:-/home/noah/discordbot/teto-private/data}"
REQUEST="${REQUEST:-$BOT_DATA/igembed.heal}"
RESULT="${RESULT:-$BOT_DATA/igembed.heal.result}"
LOG="${LOG:-$BOT_DATA/igembed-heal.log}"
STATE="${STATE:-/var/lib/igembed-heal/last}"
CDP_PORT="${CDP_PORT:-9222}"
PORT="${PORT:-8095}"
BOT_UID="${BOT_UID:-1000}"
COOKIE_UID="${COOKIE_UID:-10001}"
COOLDOWN="${COOLDOWN:-180}"
LOCK="${LOCK:-/var/lock/igembed-heal.lock}"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

requested_at_json=null
action=none
detail="healer failed unexpectedly"
healed=false
have_request=false
result_written=false

log_step() {
    local line
    line="$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"
    if $DRY_RUN; then printf '[dry-run] %s\n' "$line"; else
        mkdir -p "$BOT_DATA"
        printf '%s\n' "$line" >> "$LOG"
        chown "$BOT_UID:$BOT_UID" "$LOG" 2>/dev/null || true
    fi
}

write_result() {
    $have_request || return 0
    local payload tmp
    payload="$(python3 -c 'import json,sys,time; print(json.dumps({"requested_at":json.loads(sys.argv[1]),"healed":sys.argv[2]=="true","action":sys.argv[3],"detail":sys.argv[4],"finished_at":int(time.time())},separators=(",",":")))' "$requested_at_json" "$healed" "$action" "$detail")"
    if $DRY_RUN; then
        printf '[dry-run] result %s\n' "$payload"
    else
        tmp="$RESULT.tmp.$$"
        printf '%s\n' "$payload" > "$tmp"
        chown "$BOT_UID:$BOT_UID" "$tmp"
        mv -f "$tmp" "$RESULT"
    fi
    result_written=true
}

finish() {
    local status=$?
    if $have_request && ! $result_written; then
        write_result || true
    fi
    exit "$status"
}
trap finish EXIT

mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
if ! flock -n 9; then
    log_step "another healer is already running"
    exit 0
fi

if [[ ! -f "$REQUEST" ]]; then
    log_step "request missing"
    exit 0
fi
if ! parsed="$(python3 -c 'import base64,json,sys; d=json.load(open(sys.argv[1])); assert all(k in d for k in ("shortcode","reason","requested_at")); print(base64.b64encode(str(d["shortcode"]).encode()).decode()); print(base64.b64encode(str(d["reason"]).encode()).decode()); print(json.dumps(d["requested_at"]))' "$REQUEST" 2>/dev/null)"; then
    log_step "request is unparseable"
    $DRY_RUN || rm -f "$REQUEST"
    exit 0
fi
mapfile -t fields <<< "$parsed"
shortcode="$(printf '%s' "${fields[0]}" | base64 -d)"
reason="$(printf '%s' "${fields[1]}" | base64 -d)"
requested_at_json="${fields[2]}"
have_request=true
if $DRY_RUN; then log_step "would remove request $REQUEST"; else rm -f "$REQUEST"; fi
log_step "request shortcode=$shortcode reason=$reason"

if [[ -e "$STATE" ]] && (( $(date +%s) - $(stat -c %Y "$STATE") < COOLDOWN )); then
    detail=cooldown
    log_step "cooldown active"
    write_result
    exit 0
fi
if $DRY_RUN; then log_step "would touch state $STATE"; else
    mkdir -p "$(dirname "$STATE")"
    touch "$STATE"
fi

healthy() { curl -sf -m 5 "http://127.0.0.1:$PORT/healthz" >/dev/null; }
wait_healthy() {
    local count
    for ((count=0; count<40; count++)); do
        healthy && return 0
        sleep 1
    done
    return 1
}
probe() {
    local headers value
    headers="$(mktemp)"
    if ! curl -sS -o /dev/null -D "$headers" -m 60 \
        -A 'Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)' \
        "http://127.0.0.1:$PORT/reel/$shortcode/"; then
        rm -f "$headers"
        printf 'down\n'
        return
    fi
    value="$(awk 'BEGIN{IGNORECASE=1} /^X-Igembed-Error:/{gsub("\\r",""); sub(/^[^:]*:[[:space:]]*/,""); print; exit}' "$headers")"
    rm -f "$headers"
    printf '%s\n' "$value"
}
docker_run() {
    if $DRY_RUN; then log_step "would run: docker compose $*"; else docker compose "$@"; fi
}

if ! healthy; then
    action=restart
    log_step "service unhealthy; force-recreating"
    docker_run up -d --force-recreate
    if ! $DRY_RUN && ! wait_healthy; then detail="service did not become healthy after restart"; exit 1; fi
fi

classification="$(probe)"
log_step "probe result=${classification:-ok}"
if [[ -z "$classification" ]]; then
    healed=true
    detail="healthy"
elif [[ "$classification" == gone ]]; then
    detail="post unavailable, nothing to heal"
else
    export_error="$(mktemp)"
    log_step "refreshing Instagram cookies"
    if $DRY_RUN; then
        log_step "would run: python3 export_cookies.py $CDP_PORT cookies.txt.new"
        action=cookies
    elif python3 export_cookies.py "$CDP_PORT" cookies.txt.new 2>"$export_error"; then
        chown "$COOKIE_UID" cookies.txt.new
        mv -f cookies.txt.new cookies.txt
        action=cookies
        detail="cookies refreshed"
    else
        action=restart
        detail="$(head -1 "$export_error")"
        log_step "cookie export failed: $detail"
        rm -f cookies.txt.new
    fi
    rm -f "$export_error"
    log_step "restarting container action=$action"
    docker_run restart
    if ! $DRY_RUN && ! wait_healthy; then detail="service did not become healthy after restart"; exit 1; fi
    classification="$(probe)"
    log_step "post-heal probe result=${classification:-ok}"
    if [[ -z "$classification" ]]; then healed=true; [[ "$detail" == "healer failed unexpectedly" ]] && detail="healthy"; else healed=false; detail="$detail; post still fails: $classification"; fi
fi

log_step "finished healed=$healed action=$action detail=$detail"
write_result
