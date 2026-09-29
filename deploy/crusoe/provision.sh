#!/usr/bin/env bash
# Install Docker, bpftrace >= 0.16 and Python deps; run the stack and the demo UI under systemd.
source "$(dirname "$0")/lib.sh"

say "host setup (scripts/setup-host.sh)"
vm "cd $REMOTE_DIR && sudo apt-get install -y -qq tmux >/dev/null && sudo scripts/setup-host.sh 2>&1 | tail -12"

say "bpftrace >= 0.16 (Ubuntu 22.04 ships 0.14)"
vm "sudo curl -fsSL -o /usr/local/bin/bpftrace '$BPFTRACE_URL' && sudo chmod +x /usr/local/bin/bpftrace \
    && sudo /usr/local/bin/bpftrace --version && sudo bpftrace -e 'BEGIN { exit(); }' >/dev/null && echo '  bpftrace works'"

say "systemd: kavach-stack (compose services) and kavach-demo (stage UI on 127.0.0.1-reachable :$DEMO_PORT)"
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
Description=Kavach stage demo UI (demo/server.py)
After=kavach-stack.service
Wants=kavach-stack.service

[Service]
User=$VM_USER
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/python3 demo/server.py --port $DEMO_PORT
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

say "pull, build, start"
vm "cd $REMOTE_DIR && sudo docker compose pull -q gateway tickets && sudo docker compose --profile contained --profile uncontained build -q"
vm "sudo systemctl daemon-reload && sudo systemctl enable --now kavach-stack kavach-demo && sudo systemctl restart kavach-stack kavach-demo"
vm "cd $REMOTE_DIR && sudo docker compose ps --format '{{.Service}}\t{{.State}}'"
