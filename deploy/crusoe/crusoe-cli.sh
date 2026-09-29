#!/usr/bin/env bash
# Run the Crusoe CLI with credentials taken from the secrets file at call time
# (no ~/.crusoe/config is written). Usage: deploy/crusoe/crusoe-cli.sh compute vms list
set -euo pipefail
source "$(dirname "$0")/config.env"
set -a; source "$SECRETS_FILE" >/dev/null 2>&1; set +a
export CRUSOE_ACCESS_KEY_ID="${CRUSOE_ACCESS_KEY:?CRUSOE_ACCESS_KEY missing from $SECRETS_FILE}"
export CRUSOE_SECRET_KEY="${CRUSOE_SECRET_KEY:?CRUSOE_SECRET_KEY missing from $SECRETS_FILE}"
exec crusoe "$@"
