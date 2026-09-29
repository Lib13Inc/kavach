#!/usr/bin/env bash
# Install Docker/bpftrace/Python deps, build the images, and run the demo stack under systemd.
source "$(dirname "$0")/lib.sh"

say "host setup (scripts/setup-host.sh)"
vm "cd $REMOTE_DIR && sudo apt-get install -y -qq tmux >/dev/null && sudo scripts/setup-host.sh"

say "systemd units: kavach-stack (compose services) and kavach-trace (trace viewer on :$TRACE_PORT)"
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
vm "sudo tee /etc/systemd/system/kavach-trace.service >/dev/null" <<UNIT
[Unit]
Description=Kavach trace viewer (static files)
After=network-online.target

[Service]
User=$VM_USER
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/python3 -m http.server $TRACE_PORT --bind 0.0.0.0
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

say "pull, build, start"
# New ssh session so the docker group membership from setup-host.sh applies.
vm "cd $REMOTE_DIR && sudo docker compose pull -q gateway tickets && sudo docker compose --profile contained --profile uncontained build -q"
vm "sudo systemctl daemon-reload && sudo systemctl enable --now kavach-stack kavach-trace && sudo systemctl restart kavach-stack"
vm "cd $REMOTE_DIR && sudo docker compose ps --format '{{.Service}}\t{{.State}}'"
echo "trace viewer: http://$VM_IP:$TRACE_PORT/trace-view/"
