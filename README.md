# Kavach — hackathon starter

A working skeleton of the "Steal the card" demo from [SPEC.md](SPEC.md). An ordinary refund
agent reads a support ticket that hides a prompt injection. Uncontained, it leaks the card
number and API key. Inside Kavach, the agent only ever sees a token, the attacker gets
nothing, and the refund still succeeds.

```
  agent (sandbox net, stand-in keys) ──► gateway (mitmproxy + kavach) ──► tickets / payments / model APIs
            │                                  │ allowlist · PAN tokenize · token→PAN swap · key swap · trace
            └── eBPF guard on the host: any connect() that isn't the proxy is logged and killed
```

## What works today

| Piece | Status | Where |
| --- | --- | --- |
| Vault: PAN detection (regex + Luhn), tokenize, detokenize per host | Tested | `kavach/vault.py` |
| Gateway policy core: allowlist, token swap, key stand-ins, trace | Tested | `kavach/gateway.py` |
| mitmproxy add-on (real on-the-wire gateway) | Tested with live HTTP | `kavach/mitm_addon.py` |
| Refund agent: gullible mock model, Anthropic, OpenAI-compatible (GLM) | Mock tested; real models need your keys | `agent/agent.py` |
| 10 attack tickets + eval gate (22 pytest checks) | Passing | `services/tickets.json`, `evals/` |
| eBPF egress guard (bpftrace): log and kill | Verified on a 6.x kernel | `ebpf/` |
| Docker Compose stack | Written; run it on your Linux host | `docker-compose.yml` |
| Trace viewer | Works on any browser | `trace-view/index.html` |

## Quick start (2 minutes, no Docker)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate
bin/kavach eval            # 10 attacks: uncontained vs Kavach, PASS/FAIL gate
bin/kavach demo --ticket 2 # narrated run of the main attack, writes trace/local-*.jsonl
pytest -q evals/
```

## Full stack (Linux host with Docker)

```bash
sudo scripts/setup-host.sh           # Ubuntu 24.04: docker, bpftrace, checks BTF/cgroup v2/kvm
cp .env.example .env                 # add real keys; only the gateway container reads them
docker compose up -d gateway tickets payments attacker
bin/kavach run --uncontained --ticket 2    # watch: docker compose logs -f attacker
bin/kavach run --ticket 2                  # contained
sudo ebpf/guard.sh                         # 2nd terminal, before the contained run: kill on violation
bin/kavach run --ticket 5                  # raw-socket attack: eBPF kills the agent
```

Stage version: `scripts/demo.sh 2 mock` walks the three beats with pauses.
Swap the model: `bin/kavach run --ticket 2 --model anthropic` (or `openai`; set
`OPENAI_BASE_URL` for GLM). Frontier models often refuse obvious injections, which is why
the default is a deterministic "gullible" model: containment has to hold on the day the
model does not refuse.

Trace: `python3 -m http.server 8000` from the repo root, open
<http://localhost:8000/trace-view/>. It auto-loads `trace/*.jsonl`.

## How containment works

1. **Sandbox network.** The agent container sits on an `internal: true` Docker network. Its
   only reachable host is the gateway. It runs read-only, with no capabilities and a PID cap.
2. **Gateway.** `HTTP(S)_PROXY` points at mitmproxy running the Kavach add-on. The agent
   trusts the gateway's CA, so HTTPS to model APIs is inspected too.
3. **Tokens, not data.** Ticket responses are tokenized before the agent sees them
   (`tok_4242_a1b2c3_4242`). The token becomes the real PAN only on requests to
   `payments.internal`.
4. **Stand-in keys.** The agent holds `sk-kavach-standin-*`. The gateway swaps in the real
   key only for the matching provider host; anywhere else, the request is blocked.
5. **eBPF.** `ebpf/guard.sh` attaches to the agent container's cgroup and kills any
   `connect()` that is not to port 8080 (proxy) or 53 (DNS).

`payments.internal` is a mock card processor; a real Stripe integration would use its own
tokens. Use test card numbers only.

## Team split (from the spec)

| Role | Owns |
| --- | --- |
| Gateway and vault | `kavach/gateway.py`, `vault.py`, `mitm_addon.py`, `policy/` |
| Sandbox and eBPF | `docker-compose.yml`, `sandbox/`, `ebpf/`, `scripts/setup-host.sh` |
| Agent and evals | `agent/`, `services/tickets.json`, `evals/` |
| Trace and demo | `trace-view/`, `scripts/demo.sh`, the pitch |

## Stretch ideas

- Approval gate: refunds over `approvals.refund_over_usd` wait for a click in the trace view.
- Firecracker instead of Docker for the agent (needs `/dev/kvm`; AWS C8i/M8i/R8i work).
- Crisis guardrail and memoir faithfulness packs (see SPEC.md).
