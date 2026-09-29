#!/usr/bin/env bash
# Stop and delete the demo VM. Asks first; checks the VMID really is the demo VM.
source "$(dirname "$0")/lib.sh"
pve "qm config $VMID | grep -q '^name: $VM_NAME\$'" || { echo "VM $VMID is not $VM_NAME (or absent); nothing done"; exit 1; }
read -rp "Destroy VM $VMID ($VM_NAME) on $PVE_HOST? [y/N] " a
[[ "$a" == y || "$a" == Y ]] || exit 0
pve "qm stop $VMID --skiplock 1 2>/dev/null; qm destroy $VMID --purge 1"
