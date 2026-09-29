# Shared helpers; sourced by the scripts in this directory.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
# shellcheck source=config.env
source "$HERE/config.env"
REMOTE_DIR="/home/$VM_USER/kavach"

pve() { ssh -o BatchMode=yes "$PVE_HOST" "$@"; }
# The VM is rebuilt from scratch, so its host key changes; keep it out of known_hosts.
VM_SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
vm() { ssh "${VM_SSH_OPTS[@]}" "$VM_USER@$VM_IP" "$@"; }
say() { printf '\n== %s\n' "$*"; }
