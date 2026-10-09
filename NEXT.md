# What's next

State as of Oct 9, 2026 (commit `fabbbe1`). Hackathon demo is done; this is the follow-up list.

## Finish what's half-verified

- [ ] **OpenShell native mode, live.** `kavach openshell compile --mode native` validates against the schema but has never run in a real sandbox. Needs one OpenShell provider per secret, then a live ticket-2 run.
- [ ] **`kavach-vault` middleware.** Native mode can't tokenize cards without it; OpenShell's `network_middlewares` accepts a gateway-registered service, but none exists. Build it (or document gateway mode as the only tokenizing path).
- [ ] **HTTPS model calls inside an OpenShell sandbox.** Needs the mitmproxy CA baked into the agent image. Only HTTP (Ollama/llama-server) was tested live.
- [ ] **Run the Kyverno CEL lint** (`policy/lint/kavach-pack.kyverno.yaml`) through the Kyverno CLI; install it and fix any JSON-mode flag drift.
- [ ] **Stream OpenShell logs properly.** `follow()` polls `openshell logs` (30-line buffer per sandbox). Use the gRPC cursor stream via the OpenShell Python SDK.
- [ ] **Run the OpenShell `up` path from the demo UI on the homelab** with a screen recording; replay is the fallback, live is the pitch.

## Demo and deck

- [ ] Make the "real model takes the bait" step reliable: local llama3.x on the Mac refuses or ignores the bait and doesn't call tools; Qwen3-30B on the homelab does follow it. Either demo only on the homelab or pick a model that follows.
- [ ] Re-record or refresh the slides screenshots / add a wire-log screenshot to the deck.
- [ ] Clean up the leftover `kavach-demo` OpenShell sandbox container on the homelab VM.

## Product

- [ ] **Policy engine:** move per-request rules to CEL / Kyverno JSON mode once its engine SDK ships; keep plain YAML for the simple cases.
- [ ] **`kavach run --policy x.yaml -- python agent.py`:** wrap any process, not just the refund agent (the roadmap line on the slides).
- [ ] **Audit mode rollout flow:** `egress.mode: audit` → report → flip to enforce, with `kavach policy report` output feeding the decision.
- [ ] **Approval gate** for refunds over `approvals.refund_over_usd` (stretch idea in the README).
- [ ] **Healthcare-MH pack:** `policy/healthcare-mh.yaml` is still an untracked draft (clinical sign-off needed on crisis scripts before anything ships).
- [ ] OTel / OCSF export of the wire log for SIEMs (the spec promises it).

## Housekeeping

- [ ] Remove the leftover Crusoe deploy scripts (`deploy/crusoe/`) and Crusoe entries in `policy/payments.yaml` if they're not coming back.
- [ ] `deploy/local/policy/payments-local.yaml` is a hand-kept copy of `payments.yaml`; generate it instead.
- [ ] The OpenShell gateway needs `loginctl enable-linger` and takes ~40 s to start; fold that into `deploy/homelab/provision.sh` so a rebuilt VM works first time.
- [ ] Design partners: healthcare, education, payments.
