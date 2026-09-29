# deploy/homelab

Runs the full Kavach "Steal the card" demo on a dedicated VM on the Proxmox host **minipve**,
with the local **Qwen3-30B-A3B** (llama.cpp `llama-server` on minipve2) as a real model
alongside `--model mock`.

| | |
| --- | --- |
| VM | `kavach-demo`, VMID 130, cloned from template 9000 (Ubuntu 24.04), 4 vCPU (`cpu=host`), 8 GB, 40 GB |
| Address | 172.16.0.170 (static), user `ubuntu`, your `~/.ssh/id_ed25519` |
| Model | `http://172.16.0.44:8080/v1`, `qwen3-30b-a3b` (ai-inference LXC 200 on minipve2) |
| Stage demo | https://kavach-demo.bettong-beta.ts.net/ on the tailnet, or http://172.16.0.170:8088/ on the LAN |
| Trace viewer | `/trace-view/` on the same server (loads the live `trace/*.jsonl`) |

All settings live in `config.env`.

## Use

```sh
deploy/homelab/create-vm.sh   # clone + boot the VM (idempotent)
deploy/homelab/sync.sh        # rsync the repo, write .env once, rebuild agent images
deploy/homelab/provision.sh   # setup-host.sh, build, systemd: kavach-stack + kavach-trace
deploy/homelab/test.sh        # end-to-end checks (--no-llm to skip the model runs)
deploy/homelab/tailscale.sh   # join the tailnet as kavach-demo, serve the demo over HTTPS (login once)
deploy/homelab/demo.sh 2 openai   # terminal version of the demo in tmux, eBPF guard in the right pane
deploy/homelab/destroy.sh     # delete the VM (asks first)
```

After code changes, `sync.sh` then `test.sh` is enough.

## The stage demo

`demo/server.py` (systemd unit `kavach-demo`) serves the presenter UI. It walks through the steps in
[`demo/SCRIPT.md`](../../demo/SCRIPT.md): the notes are what to say, **Run** runs the step on the VM
(uncontained, inside Kavach with the eBPF guard armed, or the eval gate) and streams the trace into three
lanes: Sandbox, Kavach, Outside. The card at the bottom shows what the attacker walked away with.
Keys: `←` `→` steps, `Enter` run, `N` hide notes. Edit `SCRIPT.md` and `sync.sh` to change the script.

The server only accepts those three run kinds, known ticket ids and the two models. It listens on
the LAN (port 8088), and on the tailnet through `tailscale serve`.

## What `test.sh` checks

- `kavach eval`: 10/10 cases pass the gate.
- Ticket 2 with the mock and with Qwen: uncontained leaks the card; inside Kavach the attacker
  gets nothing, the model call and the refund both go through the gateway, and the refund succeeds.
  (Qwen does follow the hidden injection when uncontained; that is reported as info, not a failure.)
- Ticket 5: the eBPF guard sees the raw `connect()` that bypasses the proxy and kills the agent (exit 137).

## How it differs from the stock stack

- `docker-compose.homelab.yml` (enabled via `COMPOSE_FILE` in the VM's `.env`) points the gateway at
  `policy/payments-homelab.yaml`, which adds `172.16.0.44` to the egress allowlist, to the hosts that get
  PANs tokenized, and to where the OpenAI stand-in key may go. If the llama-server moves, update that
  file and `LLM_BASE_URL` in `config.env` (the ai-inference LXC uses DHCP, so give it a reservation).
- `.env` sets `KAVACH_HTTP_TIMEOUT=300` (local model turns are slow) and `KAVACH_START_DELAY=4`
  so `ebpf/guard.sh` attaches before the contained agent's first `connect()`.
- The VM's `.env` is never overwritten by `sync.sh`; put an `ANTHROPIC_API_KEY` there to try `--model anthropic`.
