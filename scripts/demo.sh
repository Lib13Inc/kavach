#!/usr/bin/env bash
# The 3-minute stage demo. Run in one terminal; run `sudo ebpf/guard.sh` in a second.
#   scripts/demo.sh [ticket] [model]
set -euo pipefail
cd "$(dirname "$0")/.."
T="${1:-2}"; M="${2:-mock}"
pause(){ read -rp $'\n[enter] '"$1"; }

rm -f trace/*.jsonl
docker compose up -d gateway tickets payments attacker >/dev/null
docker compose logs -f attacker 2>/dev/null | grep --line-buffered "ATTACKER RECEIVED" &
LOGPID=$!; trap 'kill $LOGPID 2>/dev/null' EXIT

pause "1/3 run the agent UNCONTAINED on ticket $T"
bin/kavach run --uncontained --ticket "$T" --model "$M"

pause "2/3 same agent, same ticket, INSIDE KAVACH"
bin/kavach run --ticket "$T" --model "$M"

pause "3/3 eval gate"
bin/kavach eval || true
echo -e "\nOpen trace-view/index.html and load trace/*.jsonl for the timeline."
