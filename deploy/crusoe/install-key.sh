#!/usr/bin/env bash
# Put the real Crusoe Managed Inference key into the VM's .env, where only the gateway
# container reads it, then recreate the gateway. The key travels over SSH stdin: never in
# argv, never printed. The agent only ever holds the stand-in sk-kavach-standin-crusoe.
source "$(dirname "$0")/lib.sh"
[[ -n "$(secret CRUSOE_AI_KEY)" ]] || { echo "CRUSOE_AI_KEY not found in $SECRETS_FILE"; exit 1; }

say "check the key against $CRUSOE_BASE_URL"
# curl reads the header from a config on stdin, so the key never appears in argv.
code=$(secret CRUSOE_AI_KEY | sed 's/.*/header = "Authorization: Bearer &"/' \
       | curl -s -K - -o /dev/null -w '%{http_code}' -m 20 "$CRUSOE_BASE_URL/models")
[[ "$code" == 200 ]] || { echo "Crusoe returned HTTP $code for the key"; exit 1; }
echo "  key accepted"

say "install it in $REMOTE_DIR/.env (mode 600) and recreate the gateway"
secret CRUSOE_AI_KEY | vm "cd $REMOTE_DIR && python3 -c '
import os, sys
key = sys.stdin.read().strip()
lines = [l for l in open(\".env\").read().splitlines() if not l.startswith(\"CRUSOE_API_KEY=\")]
lines.append(\"CRUSOE_API_KEY=\" + key)
fd = os.open(\".env\", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, (\"\\n\".join(lines) + \"\\n\").encode()); os.close(fd)
'"
vm "cd $REMOTE_DIR && sudo docker compose up -d --force-recreate gateway 2>&1 | tail -1 && sudo systemctl restart kavach-demo"
