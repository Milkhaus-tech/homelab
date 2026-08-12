#!/bin/bash

# Default ports for your homelab
DEFAULT_PORTS=("16261" "16262" "34197" "23570" "23571" "23572" "23573" "23574" "23575" "23576" "23577" "23578" "23579" "23580")

# ANSI colors
COLORS=(
    "\e[31m"  # Red
    "\e[32m"  # Green
    "\e[33m"  # Yellow
    "\e[34m"  # Blue
    "\e[35m"  # Magenta
    "\e[36m"  # Cyan
    "\e[91m"  # Bright Red
    "\e[92m"  # Bright Green
    "\e[93m"  # Bright Yellow
    "\e[94m"  # Bright Blue
    "\e[95m"  # Bright Magenta
    "\e[96m"  # Bright Cyan
)

RESET="\e[0m"

echo "Port Watcher"
echo "============"
echo "Press ENTER to use default ports, or type a space-separated list (e.g. 16261 16262 34197)"
read -p "Ports to monitor: " USER_PORTS

if [ -z "$USER_PORTS" ]; then
    PORTS=("${DEFAULT_PORTS[@]}")
    echo "Using default ports: ${PORTS[*]}"
else
    PORTS=($USER_PORTS)
    echo "Using custom ports: ${PORTS[*]}"
fi

# Build tcpdump filter
FILTER=""
for PORT in "${PORTS[@]}"; do
    if [ -z "$FILTER" ]; then
        FILTER="udp port $PORT"
    else
        FILTER="$FILTER or udp port $PORT"
    fi
done

echo -e "\nStarting tcpdump on wg0..."
echo -e "Color legend:\n"

# Assign colors to ports
declare -A PORT_COLORS
i=0
for PORT in "${PORTS[@]}"; do
    COLOR=${COLORS[$((i % ${#COLORS[@]}))]}
    PORT_COLORS[$PORT]=$COLOR
    echo -e "$(printf "${COLOR}")Port $PORT$(printf "${RESET}")"
    ((i++))
done

echo -e "\nListening...\n"

# Run tcpdump and colorize only the port number
sudo tcpdump -n -i wg0 $FILTER 2>/dev/null | while read -r line; do
    for PORT in "${PORTS[@]}"; do
        if [[ "$line" =~ \.${PORT}: ]]; then
            COLOR=${PORT_COLORS[$PORT]}
            COLORED_LINE=$(echo "$line" | sed "s/\.${PORT}:/. $(printf "${COLOR}")${PORT}$(printf "${RESET}"):/")
            echo -e "$COLORED_LINE"
            break
        fi
    done
done
