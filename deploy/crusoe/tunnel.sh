#!/usr/bin/env bash
# Open the demo UI through SSH (port 8088 is closed in Crusoe's firewall): http://localhost:8088/
source "$(dirname "$0")/lib.sh"
ensure_ip
echo "demo UI: http://localhost:$DEMO_PORT/   (Ctrl-C to close the tunnel)"
exec ssh "${VM_SSH_OPTS[@]}" -N -L "$DEMO_PORT:127.0.0.1:$DEMO_PORT" "$VM_USER@$VM_IP"
