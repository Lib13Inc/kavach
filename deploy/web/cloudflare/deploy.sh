#!/usr/bin/env bash
# Build web/ from SPEC.md and deploy it to kavach.lib13.com via Wrangler.
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm install
python3 build.py
npx wrangler deploy "$@"
