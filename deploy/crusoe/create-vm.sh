#!/usr/bin/env bash
# Create the Crusoe VM (c1a.4x, Ubuntu 22.04) and wait for SSH. Safe to re-run.
source "$(dirname "$0")/lib.sh"

if vm_json >/dev/null; then
  say "VM $VM_NAME already exists"
else
  say "creating $VM_NAME ($VM_TYPE, $LOCATION, $IMAGE) — about \$0.16/hour until destroy.sh"
  crusoe_cli compute vms create --name "$VM_NAME" --type "$VM_TYPE" --location "$LOCATION" \
    --image "$IMAGE" --keyfile "$SSH_PUBKEY" 2>&1 | tail -3
fi

VM_IP="$(vm_ip)"
echo "  public IP $VM_IP (only SSH is open)"
say "waiting for ssh"
for _ in $(seq 1 60); do vm true 2>/dev/null && break; sleep 5; done
vm "cloud-init status --wait >/dev/null 2>&1 || true; uname -r; nproc; free -g | awk '/Mem/{print \$2\" GiB RAM\"}'; df -h / | tail -1"
