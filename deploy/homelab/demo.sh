#!/usr/bin/env bash
# Open the stage demo on the VM in tmux: scripts/demo.sh on the left, eBPF guard on the right.
#   ./demo.sh [ticket] [mock|openai]
source "$(dirname "$0")/lib.sh"
T="${1:-2}"; M="${2:-mock}"
echo "trace viewer: http://$VM_IP:$TRACE_PORT/trace-view/"
ssh -t "${VM_SSH_OPTS[@]}" "$VM_USER@$VM_IP" \
  "cd $REMOTE_DIR && tmux kill-session -t kavach 2>/dev/null; \
   tmux new-session -s kavach 'sudo -E scripts/demo.sh $T $M; bash' \; \
        split-window -h 'sudo ebpf/guard.sh; bash' \; select-pane -L"
