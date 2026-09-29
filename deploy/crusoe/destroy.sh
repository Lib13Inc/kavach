#!/usr/bin/env bash
# Delete the Crusoe VM (stops billing). Asks first.
source "$(dirname "$0")/lib.sh"
vm_json >/dev/null || { echo "VM $VM_NAME not found; nothing to do"; exit 0; }
read -rp "Delete Crusoe VM $VM_NAME? This stops billing and loses its disk. [y/N] " a
[[ "$a" == y || "$a" == Y ]] || exit 0
crusoe_cli compute vms delete "$VM_NAME"
