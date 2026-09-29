# deploy/crusoe

Runs the full Kavach demo on **Crusoe Cloud**, independent of the homelab: a CPU VM runs the
stack (gateway, sandbox, eBPF guard, stage UI), and **Crusoe Managed Inference** (Crusoe's Qwen,
`Qwen/Qwen3.8-27B`) is the model behind `--model crusoe`.

| | |
| --- | --- |
| VM | `kavach-crusoe`, `c1a.4x` (4 vCPU, 16 GB, about $0.16/hour), `us-east1-a`, Ubuntu 22.04 |
| Model | `https://api.inference.crusoecloud.com/v1`, `Qwen/Qwen3.8-27B` |
| Demo UI | https://kavach-crusoe.bettong-beta.ts.net/ after `tailscale.sh`, or `./tunnel.sh` then http://localhost:8088/ |
| Credentials | `~/.env.secrets`: `CRUSOE_ACCESS_KEY`, `CRUSOE_SECRET_KEY` (VMs), `CRUSOE_AI_KEY` (inference). Read at call time; nothing is written to `~/.crusoe` or the repo. |

## Use

```sh
brew install crusoecloud/cli/crusoe   # once
deploy/crusoe/deploy.sh               # create-vm, sync, provision, install-key, test
deploy/crusoe/tailscale.sh            # join the tailnet and serve the UI over HTTPS (approve once)
deploy/crusoe/tunnel.sh               # or: SSH tunnel to the UI
deploy/crusoe/destroy.sh              # delete the VM and stop billing
deploy/crusoe/crusoe-cli.sh compute vms list   # any Crusoe CLI command, with the credentials applied
```

After code changes: `sync.sh`, then `test.sh`.

## How the model key is handled

- `install-key.sh` sends the real inference key over SSH stdin into the VM's `.env` (mode 600). It never
  appears in a command line or in output.
- Only the gateway container gets the real key. The agent holds the stand-in `sk-kavach-standin-crusoe`;
  the policy swaps it for the real key on calls to `api.inference.crusoecloud.com` only, and blocks it anywhere else.
- The uncontained agent never gets the real key, so Crusoe runs only inside Kavach. `test.sh` checks that the
  key appears in no trace file and that the agent container only holds the stand-in.

## Differences from the homelab

- Ubuntu 22.04 (Crusoe's only plain x86 image) ships bpftrace 0.14; `provision.sh` installs the static
  v0.27 build, since the eBPF guard needs 0.16 or newer.
- Only SSH is open in Crusoe's firewall. The demo UI can start runs, so it is not exposed publicly:
  use the tailnet or the SSH tunnel.
- No local model; the demo steps that use the homelab's local Qwen are greyed out in the UI.

## Status

The first deploy stopped at VM creation: the project has no quota for General-Purpose CPU (C1A)
instances. Request a C1A quota (4 vCPU is enough) from Crusoe support, then run `deploy.sh`.
