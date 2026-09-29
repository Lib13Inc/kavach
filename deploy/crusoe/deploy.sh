#!/usr/bin/env bash
# Full Crusoe deploy: VM, code, host setup, model key, end-to-end test.
#   deploy/crusoe/deploy.sh        then: ./tailscale.sh (or ./tunnel.sh) to open the demo UI
set -euo pipefail
cd "$(dirname "$0")"
./create-vm.sh
./sync.sh
./provision.sh
./install-key.sh
./test.sh
