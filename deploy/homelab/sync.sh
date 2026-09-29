#!/usr/bin/env bash
# Copy the working tree to the VM. The VM's .env is created once and never overwritten,
# so model keys you add there survive re-syncs.
source "$(dirname "$0")/lib.sh"

say "rsync $REPO -> $VM_IP:$REMOTE_DIR"
vm "command -v rsync >/dev/null || (sudo apt-get update -qq && sudo apt-get install -y -qq rsync)"
rsync -az --delete -e "ssh ${VM_SSH_OPTS[*]}" \
  --exclude .git --exclude .venv --exclude node_modules --exclude .wrangler \
  --exclude '__pycache__' --exclude .env --exclude 'trace/*.jsonl' \
  "$REPO/" "$VM_USER@$VM_IP:$REMOTE_DIR/"
# rsync -a copies the local trace/ mode; containers (agent runs as uid 10001) must write there.
vm "chmod 777 $REMOTE_DIR/trace"

say "ensure $REMOTE_DIR/.env"
vm "cd $REMOTE_DIR && [ -f .env ] || cat > .env" <<ENV
# Written by deploy/homelab/sync.sh on first sync; edit freely, it is never overwritten.
COMPOSE_FILE=docker-compose.yml:deploy/homelab/docker-compose.homelab.yml

# --model openai -> llama-server on minipve2 (no key needed; the gateway still swaps the stand-in).
OPENAI_BASE_URL=$LLM_BASE_URL
OPENAI_MODEL=$LLM_MODEL
OPENAI_API_KEY=
KAVACH_HTTP_TIMEOUT=300
# Lets the eBPF guard attach to the contained agent before its first connect().
KAVACH_START_DELAY=4

# --model anthropic (optional): the real key lives only in the gateway container.
ANTHROPIC_API_KEY=
ENV

# The agent images COPY agent/ and kavach/ at build time; rebuild so runs use the synced code.
# (The gateway and services mount the code, so a restart picks it up.)
if vm "command -v docker >/dev/null"; then
  say "rebuild agent images, restart stack"
  vm "cd $REMOTE_DIR && sudo docker compose --profile contained --profile uncontained build -q && sudo systemctl restart kavach-stack; sudo systemctl try-restart kavach-demo 2>/dev/null || true"
fi
