# Kavach on NVIDIA OpenShell

[OpenShell](https://github.com/NVIDIA/OpenShell) (a CNCF project) runs an agent in a sandbox:
Landlock for files, seccomp, a non-root user, and a supervisor that checks every outbound connection
against a YAML policy. Kavach can use it instead of the Docker internal network and the eBPF guard.

| | Docker + eBPF (default) | OpenShell |
| --- | --- | --- |
| Isolation | internal network, read-only FS, no caps | Landlock, seccomp, supervisor, network fence |
| "Around the gateway" attempts | eBPF logs and kills the process | OpenShell denies the connection and logs it (`NET:OPEN DENIED`) |
| Card tokenization, key swap, wire log | Kavach gateway | Kavach gateway (OpenShell has no PAN vault) |
| Audit stream | Kavach trace | Kavach trace + OpenShell OCSF events, one timeline |

## Use it

```bash
kavach openshell compile                      # gateway mode: the only allowed destination is the Kavach gateway
kavach openshell compile --mode native        # OpenShell enforces the allowlist per host, with its own providers
kavach openshell validate policy/openshell/payments-gateway.yaml
kavach openshell up --image kavach-agent --ticket 2   # sandbox create + agent as the main process (--dry-run to preview)
kavach openshell logs --name kavach-agent     # tail OCSF events into trace/openshell.jsonl for the wire log
kavach openshell replay --ticket 5            # demo fallback, see below
```

Gateway mode needs the Kavach gateway reachable from the sandbox: use `deploy/local/docker-compose.local.yml`,
which publishes it on port 8080. Pass `--gateway-host` with whatever name your sandbox uses for the host.

## What was tested

**Live, on the homelab VM (OpenShell 0.1.3, Docker compute driver)** via `deploy/homelab/test.sh`:

- the agent runs inside a real OpenShell sandbox built from the Kavach agent image, with only the Kavach gateway reachable;
- the refund succeeds with a token, the exfiltration POST is blocked by Kavach, and Qwen3-30B works through the same path;
- OpenShell's real OCSF events (`NET:OPEN [INFO] ALLOWED … host.openshell.internal:8080`, `NET:OPEN [MED] DENIED … 172.28.0.66:9999 [reason:transparent_tcp_policy_denied]`) are parsed into the wire log.

Also unit-tested (`evals/test_extensions.py`): compiled policies against the documented schema rules, and the log parser on lines captured from that live run.

## What running it live taught us (all fixed)

- The compiled gateway endpoint needs `tls: skip`. Without it OpenShell inspects the HTTP inside the tunnel and rejects forward-proxy requests (`request_authority_mismatch`).
- A named `process.run_as_user` must exist in the image (OpenShell checks). The compiler now defaults to the image's `USER`; `--run-as` overrides.
- The image's workdir must be writable by the agent's user, so the Dockerfile `chown`s `/app`, and `include_workdir` is on.
- `host.openshell.internal` resolves to the **gateway host's loopback**, so the Kavach gateway must be published on `127.0.0.1:8080` (see `deploy/homelab/docker-compose.homelab.yml`).
- Live log lines come as `[epoch] [sandbox] [OCSF ] [ocsf] NET:OPEN …`, and as `ISO-time OCSF …` on a sandbox's own stderr. Both parse.
- OpenShell sandboxes inherit the image's compose label, so `ebpf/guard.sh` must skip `openshell-*` containers (it does now).
- The OpenShell gateway is a systemd **user** service: enable lingering (`sudo loginctl enable-linger $USER`) or it stops when your last login ends. It takes ~40 s to come up.
- `openshell logs` shows only the last 30 lines per sandbox, so `follow()` polls fast and de-duplicates.

## Still assumed or untested

- `--mode native` (OpenShell enforcing the allowlist itself, with its own credential providers) validates against the schema but has not been run live.
- The `kavach-vault` middleware (`--middleware`) assumes a gateway-registered middleware service. None ships yet.
- HTTPS model calls from inside the sandbox need the mitmproxy CA baked into the image.
- Agent events leave the sandbox as `@@kavach {json}` lines on stdout (`KAVACH_AGENT_TRACE=-`).

`kavach openshell replay` is the stage fallback for hosts without OpenShell: a real in-process Kavach run beside a log modelled on the live one.
Every event it produces carries `replayed: true`, and the demo UI badges it.
