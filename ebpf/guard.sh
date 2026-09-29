#!/usr/bin/env bash
# Attach the eBPF egress guard to the running contained agent container.
#   sudo ebpf/guard.sh            # enforce (kill on violation)
#   sudo ebpf/guard.sh --log-only
# Events are appended to trace/ebpf.jsonl for the trace view.
set -euo pipefail
cd "$(dirname "$0")/.."
ENFORCE=1; [[ "${1:-}" == "--log-only" ]] && ENFORCE=0

echo "waiting for the contained agent container..."
for _ in $(seq 1 60); do
  CID=$(docker ps -q --filter "label=com.docker.compose.service=agent" | head -1)
  [[ -n "$CID" ]] && break; sleep 0.5
done
[[ -z "${CID:-}" ]] && { echo "no agent container running"; exit 1; }
FULL=$(docker inspect -f '{{.Id}}' "$CID")

# cgroup v2 path: systemd driver first, cgroupfs driver as fallback.
for P in "/sys/fs/cgroup/system.slice/docker-${FULL}.scope" "/sys/fs/cgroup/docker/${FULL}"; do
  [[ -d "$P" ]] && CG="$P" && break
done
[[ -z "${CG:-}" ]] && { echo "cgroup for $FULL not found (cgroup v2 required)"; exit 1; }

echo "attaching to $CG (enforce=$ENFORCE)"
bpftrace --unsafe ebpf/egress_guard.bt "$CG" "$ENFORCE" \
  | grep --line-buffered '^{' | tee -a trace/ebpf.jsonl
