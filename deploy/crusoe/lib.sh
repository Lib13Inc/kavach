# Shared helpers; sourced by the scripts in this directory.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
# shellcheck source=config.env
source "$HERE/config.env"
REMOTE_DIR="/home/$VM_USER/kavach"

crusoe_cli() { "$HERE/crusoe-cli.sh" "$@"; }
say() { printf '\n== %s\n' "$*"; }

# Read one variable from the secrets file without exporting the rest or printing it.
secret() { (set -a; source "$SECRETS_FILE" >/dev/null 2>&1; printenv "$1") || true; }

vm_json() { crusoe_cli compute vms get "$VM_NAME" --json 2>/dev/null; }
vm_ip() {
  vm_json | python3 -c '
import json, sys
d = json.load(sys.stdin); d = d[0] if isinstance(d, list) else d
for iface in d.get("network_interfaces", []):
    for ip in iface.get("ips", []):
        pub = (ip.get("public_ipv4") or {}).get("address")
        if pub: print(pub); sys.exit()
sys.exit(1)'
}
VM_IP="${VM_IP:-}"
ensure_ip() { [[ -n "$VM_IP" ]] || VM_IP="$(vm_ip)" || { echo "VM $VM_NAME not found; run create-vm.sh"; exit 1; }; }

# Crusoe VMs get new host keys when rebuilt; keep them out of known_hosts.
VM_SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10)
vm() { ensure_ip; ssh "${VM_SSH_OPTS[@]}" "$VM_USER@$VM_IP" "$@"; }
