#!/bin/bash

# Default ports for your homelab
DEFAULT_PORTS=("16261" "16262" "34197" "23570" "23571" "23572" "23573" "23574" "23575" "23576" "23577" "23578" "23579" "23580")

# ANSI colors
COLORS=(
    "\e[31m" "\e[32m" "\e[33m" "\e[34m" "\e[35m" "\e[36m"
    "\e[91m" "\e[92m" "\e[93m" "\e[94m" "\e[95m" "\e[96m"
)

RESET="\e[0m"

echo "Port Watcher (Tally Mode)"
echo "========================="
echo "Press ENTER to use default ports, or type a space-separated list:"
read -p "Ports to monitor: " USER_PORTS

if [ -z "$USER_PORTS" ]; then
    PORTS=("${DEFAULT_PORTS[@]}")
else
    PORTS=($USER_PORTS)
fi

# Build tcpdump filter
FILTER=""
for PORT in "${PORTS[@]}"; do
    [[ -z "$FILTER" ]] && FILTER="udp port $PORT" || FILTER="$FILTER or udp port $PORT"
done

# Assign colors + counters
declare -A PORT_COLORS
declare -A PORT_COUNTS

i=0
for PORT in "${PORTS[@]}"; do
    PORT_COLORS[$PORT]=${COLORS[$((i % ${#COLORS[@]}))]}
    PORT_COUNTS[$PORT]=0
    ((i++))
done

# Read tcpdump via fd 3 so counters update in THIS shell (a pipe would fork a
# subshell and the dashboard would read zeros forever)
exec 3< <(sudo tcpdump -n -l -i wg0 $FILTER 2>/dev/null)
TCPDUMP_PID=$!
trap 'exec 3<&-; sudo pkill -P $TCPDUMP_PID 2>/dev/null; exit' INT TERM

NEXT_DRAW=0
while true; do
    if read -r -t 0.2 line <&3; then
        for PORT in "${PORTS[@]}"; do
            if [[ "$line" =~ \.${PORT}: ]]; then
                ((PORT_COUNTS[$PORT]++))
            fi
        done
    elif (( $? == 1 )); then
        echo "tcpdump exited — check sudo access and that wg0 is up"
        break
    fi

    if (( SECONDS >= NEXT_DRAW )); then
        NEXT_DRAW=$((SECONDS + 1))
        printf "\e[H\e[2J"   # Clear screen without flicker
        echo "Port Watcher (Tally Mode)"
        echo "========================="
        echo "Interface: wg0"
        echo "Updated: $(date '+%H:%M:%S')"
        echo ""

        for PORT in "${PORTS[@]}"; do
            COLOR=${PORT_COLORS[$PORT]}
            COUNT=${PORT_COUNTS[$PORT]}
            printf "%bPort %s%b : %d packets\n" "$COLOR" "$PORT" "$RESET" "$COUNT"
        done
    fi
done
