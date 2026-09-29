#!/usr/bin/env bash
# Copy the working tree to the VM, write its .env once, rebuild the agent images if Docker is set up.
source "$(dirname "$0")/lib.sh"

ensure_ip
say "rsync $REPO -> $VM_IP:$REMOTE_DIR"
vm "command -v rsync >/dev/null || (sudo apt-get update -qq && sudo apt-get install -y -qq rsync >/dev/null)"
rsync -az --delete -e "ssh ${VM_SSH_OPTS[*]}" \
  --exclude .git --exclude .venv --exclude node_modules --exclude .wrangler \
  --exclude '__pycache__' --exclude .env --exclude 'trace/*.jsonl' \
  "$REPO/" "$VM_USER@$VM_IP:$REMOTE_DIR/"
# rsync copies the local trace/ mode; the agent container (uid 10001) must write there.
vm "chmod 777 $REMOTE_DIR/trace"

say "ensure $REMOTE_DIR/.env (the Crusoe key is added by install-key.sh)"
vm "cd $REMOTE_DIR && [ -f .env ] || (umask 077 && cat > .env)" <<ENV
# Written by deploy/crusoe/sync.sh on first sync; never overwritten.
CRUSOE_BASE_URL=$CRUSOE_BASE_URL
CRUSOE_MODEL=$CRUSOE_MODEL
KAVACH_HTTP_TIMEOUT=120
# Lets the eBPF guard attach to the contained agent before its first connect().
KAVACH_START_DELAY=4
ENV

if vm "command -v docker >/dev/null"; then
  say "rebuild agent images, restart stack and demo UI"
  vm "cd $REMOTE_DIR && sudo docker compose --profile contained --profile uncontained build -q \
      && sudo systemctl try-restart kavach-stack kavach-demo 2>/dev/null || true"
fi
