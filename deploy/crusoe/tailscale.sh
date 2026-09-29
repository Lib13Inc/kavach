#!/usr/bin/env bash
# Put the Crusoe VM on the tailnet and serve the demo UI at https://$TS_HOSTNAME.$TAILNET/
# First run prints a login URL to approve. Safe to re-run.
source "$(dirname "$0")/lib.sh"
vm "command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sudo sh >/dev/null 2>&1"
if ! vm "tailscale status >/dev/null 2>&1"; then
  say "log in: open the URL below and approve $TS_HOSTNAME (waits up to 10 minutes)"
  vm "sudo tailscale up --hostname=$TS_HOSTNAME --timeout=600s" || true
fi
vm "tailscale status >/dev/null 2>&1" || { echo "not logged in yet; approve the machine, then re-run"; exit 1; }
say "serve http://127.0.0.1:$DEMO_PORT at https://$TS_HOSTNAME.$TAILNET/"
vm "sudo tailscale serve --bg --https=443 http://127.0.0.1:$DEMO_PORT >/dev/null && tailscale serve status"
