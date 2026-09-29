#!/usr/bin/env bash
# Clone the Ubuntu 24.04 cloud template into the demo VM on the Proxmox host and boot it.
# Safe to re-run: an existing VM is left alone (and started if stopped).
source "$(dirname "$0")/lib.sh"

if pve "qm status $VMID" >/dev/null 2>&1; then
  say "VM $VMID already exists on $PVE_HOST"
  pve "qm config $VMID | grep -q '^name: $VM_NAME\$'" || { echo "VMID $VMID is not $VM_NAME; refusing to touch it"; exit 1; }
else
  say "cloning template $TEMPLATE_VMID -> $VMID ($VM_NAME)"
  pve "qm clone $TEMPLATE_VMID $VMID --name $VM_NAME --full 1 --storage $STORAGE"
  scp -q -o BatchMode=yes "$SSH_PUBKEY" "$PVE_HOST:/tmp/kavach-demo.pub"
  # cpu=host passes AMD-V through, so /dev/kvm exists inside the VM (Firecracker stretch goal).
  pve "qm set $VMID --cores $CORES --memory $MEMORY_MB --cpu host --onboot 1 \
        --net0 virtio,bridge=$BRIDGE \
        --ciuser $VM_USER --sshkeys /tmp/kavach-demo.pub \
        --ipconfig0 ip=$VM_IP/$VM_CIDR,gw=$VM_GW --nameserver $VM_DNS \
        --description 'Kavach demo (deploy/homelab). Safe to destroy and rebuild.' \
     && qm resize $VMID scsi0 $DISK_SIZE && rm -f /tmp/kavach-demo.pub"
fi

pve "qm status $VMID | grep -q running || qm start $VMID"

say "waiting for ssh on $VM_IP"
for _ in $(seq 1 60); do
  vm true 2>/dev/null && break; sleep 5
done
vm true || { echo "VM did not come up on $VM_IP"; exit 1; }
say "waiting for cloud-init"
vm "cloud-init status --wait >/dev/null; uname -r; nproc; free -g | awk '/Mem/{print \$2\" GiB RAM\"}'; df -h / | tail -1"
