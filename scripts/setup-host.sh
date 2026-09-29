#!/usr/bin/env bash
# One-time host setup for Ubuntu 24.04 (home lab or AWS m8i/c8i). Run with sudo.
set -euo pipefail

echo "== packages"
apt-get update -y
apt-get install -y ca-certificates curl git jq python3 python3-venv python3-pip bpftrace

if ! command -v docker >/dev/null; then
  echo "== docker"
  curl -fsSL https://get.docker.com | sh
fi
[[ -n "${SUDO_USER:-}" ]] && usermod -aG docker "$SUDO_USER" || true

echo "== python deps for kavach eval/demo"
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

echo "== checks"
ok(){ printf "  %-28s %s\n" "$1" "$2"; }
ok "kernel" "$(uname -r)"
[[ -f /sys/kernel/btf/vmlinux ]] && ok "BTF (eBPF)" "yes" || ok "BTF (eBPF)" "MISSING - eBPF guard will not load"
[[ "$(stat -fc %T /sys/fs/cgroup)" == "cgroup2fs" ]] && ok "cgroup v2" "yes" || ok "cgroup v2" "NO"
bpftrace -e 'BEGIN { exit(); }' >/dev/null 2>&1 && ok "bpftrace" "works" || ok "bpftrace" "FAILED"
[[ -e /dev/kvm ]] && ok "/dev/kvm (Firecracker)" "yes" || ok "/dev/kvm (Firecracker)" "no (fine for day one)"
docker compose version >/dev/null 2>&1 && ok "docker compose" "yes" || ok "docker compose" "MISSING"
curl -s -o /dev/null -w "%{http_code}" https://api.anthropic.com >/dev/null && ok "egress to model APIs" "yes" || ok "egress to model APIs" "NO"

mkdir -p trace && chmod 777 trace
[[ -f .env ]] || cp .env.example .env
echo "done. Log out and back in for docker group membership, then: docker compose pull"
