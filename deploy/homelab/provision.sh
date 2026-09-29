#!/usr/bin/env bash
# Install Docker/bpftrace/Python deps, build the images, and run the demo stack under systemd.
source "$(dirname "$0")/lib.sh"

say "host setup (scripts/setup-host.sh)"
vm "cd $REMOTE_DIR && sudo apt-get install -y -qq tmux >/dev/null && sudo scripts/setup-host.sh"

say "systemd units: kavach-stack (compose services) and kavach-demo (stage UI on :$TRACE_PORT)"
vm "sudo tee /etc/systemd/system/kavach-stack.service >/dev/null" <<UNIT
[Unit]
Description=Kavach demo stack (gateway, tickets, payments, attacker)
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/docker compose up -d --build gateway tickets payments attacker
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
UNIT
vm "sudo tee /etc/systemd/system/kavach-demo.service >/dev/null" <<UNIT
[Unit]
Description=Kavach stage demo UI and trace viewer (demo/server.py)
After=kavach-stack.service
Wants=kavach-stack.service

[Service]
# Runs docker (docker group) and the eBPF guard (passwordless sudo on the cloud image).
User=$VM_USER
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/python3 demo/server.py --port $TRACE_PORT
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

say "pull, build, start"
# New ssh session so the docker group membership from setup-host.sh applies.
vm "cd $REMOTE_DIR && sudo docker compose pull -q gateway tickets && sudo docker compose --profile contained --profile uncontained build -q"
vm "sudo systemctl daemon-reload && sudo systemctl disable --now kavach-trace 2>/dev/null; sudo rm -f /etc/systemd/system/kavach-trace.service; sudo systemctl daemon-reload; sudo systemctl enable --now kavach-stack kavach-demo && sudo systemctl restart kavach-stack kavach-demo"
vm "cd $REMOTE_DIR && sudo docker compose ps --format '{{.Service}}\t{{.State}}'"
echo "stage demo:   http://$VM_IP:$TRACE_PORT/   (trace viewer: /trace-view/)"
