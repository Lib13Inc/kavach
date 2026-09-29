#!/usr/bin/env bash
# Put the demo VM on the tailnet and serve the stage UI over HTTPS:
#   https://$TS_HOSTNAME.$TAILNET/
# First run prints a login URL: open it and approve the machine. Safe to re-run.
source "$(dirname "$0")/lib.sh"

say "install tailscale"
vm "command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sudo sh >/dev/null"

if ! vm "tailscale status >/dev/null 2>&1"; then
  say "log in: open the URL below and approve $TS_HOSTNAME"
  # --accept-routes=false: the VM already sits on the lab LAN; don't route it back through the tailnet.
  vm "sudo tailscale up --hostname=$TS_HOSTNAME --accept-routes=false --timeout=300s"
fi

say "serve http://127.0.0.1:$TRACE_PORT at https://$TS_HOSTNAME.$TAILNET/"
vm "sudo tailscale serve --bg --https=443 http://127.0.0.1:$TRACE_PORT >/dev/null && tailscale serve status"
