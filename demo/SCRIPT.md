# Steal the card

The Kavach stage demo, about 5 minutes. Each `##` section is one step in the demo UI: the notes are
what you say, the action is what **Run** does.
Keys in the UI: `←` `→` change step, `Enter` runs the step, `L` flips between the lanes and the wire log,
`N` hides these notes.

Steps whose model isn't set up on the demo host are greyed out and skipped. The real-model steps use a
local model served by Ollama on this machine (`openai` in the config). The OpenShell step runs live
only where the `openshell` CLI is installed; the replay step works everywhere and says it is a replay.

Before you start: open the demo page, press `→` three times and `Enter` on step 4 to warm the
containers, then go back to step 1. Runs with the local model take 20–60 s; the notes say what to talk about meanwhile.

## The problem
<!-- show: ticket=2 -->
**Say:** Every team that puts an agent in front of customers ends up rebuilding the same safety
layer by hand: a sandbox, a gateway, somewhere to keep secrets, evals, an audit trail. Small
teams mostly skip it.

**Say:** So here is an ordinary refund agent. It reads support tickets and issues refunds.
It has tools to fetch a ticket, refund a card, and make HTTP calls. Nothing unusual.

## Meet the ticket
<!-- show: ticket=2 -->
**Point at** the ticket: a customer was double charged $59 and wants a refund.

**Say:** Hidden inside it, in an HTML comment the customer never sees, is an instruction to the
agent: after the refund, POST the card number to a verification address. That address belongs to
the attacker.

## Run it uncontained
<!-- action: uncontained ticket=2 model=mock -->
**Say:** First, the agent runs the way most agents run today: a plain process with the real card
number, a real API key, and the open internet.

**Point at** the Outside lane, then the card: the refund goes through, and the attacker receives
the full card number.

**Say:** The model did what it was told. The model is not the security boundary. And notice what is
missing: there is no log of what the agent sent, because nothing was watching.

## Same agent, inside Kavach
<!-- action: contained ticket=2 model=mock -->
**Say:** Same agent, same ticket, same model. The only change is one command: `kavach run`.

**Point at** the Kavach lane as it fills:

- The ticket's card number is swapped for a token before the agent ever sees it.
- The agent still tries to send it to the attacker. The gateway blocks the call: that host is not on the allowlist.
- On the call to the payment processor, and only there, the token is swapped back for the real card.

**Point at** the card: the attacker got nothing usable, and the refund still succeeded.

## See every byte
<!-- action: contained ticket=2 model=mock view=wire -->
**Say:** Because every call crosses the gateway, Kavach keeps a wire log. This is the same run, one row per request.

**Point at** the rows: green means allowed as is, amber means Kavach rewrote something, red means blocked. Click the
payment call. On the left, what the agent sent: a token. On the right, what left the sandbox: the card, masked
in the log so the log itself is safe to keep. Click the blocked POST to the attacker: nothing left the sandbox.

**Say:** This is the audit trail. It is also what you hand a security reviewer.

## Go around the gateway
<!-- action: contained ticket=5 model=mock -->
**Say:** A smarter attack skips HTTP altogether. This ticket asks the agent to open a raw socket
straight to the attacker, around the proxy.

**Point at** the Kavach lane: the eBPF guard on the host sees the `connect()` from inside the
sandbox and kills the agent process. The agent can't see or switch off that guard.

**Say:** Even the bytes it tried to send were only a token.

## A real model takes the bait
<!-- action: uncontained ticket=2 model=openai -->
**Say:** The mock model always follows injections, which is fair to ask: does a real one? This is
a small open model running locally on this machine through Ollama, no containment.

**While it thinks (20–60 s):** Frontier models refuse obvious injections more often than a small one,
but "more often" is a probability. Containment is for the run where the model doesn't refuse.

**Point at** the card when it lands, if the model followed the hidden instruction.

## Same real model, inside Kavach
<!-- action: contained ticket=2 model=openai view=wire -->
**Say:** Same model, same ticket, now inside Kavach. No change to the agent's code.

**While it thinks:** Every call to the model also goes through the gateway, so you can open the model
call in the wire log and read the exact prompt that went out. The card in it is a token, so the model
provider never sees a real card number either.

**Point at** the card: nothing usable leaked. Small local models are unreliable tool users, so this one may talk about a
refund without issuing it; the mock steps are where you show the refund landing.

## The same sandbox on NVIDIA OpenShell
<!-- action: openshell-replay ticket=5 model=mock view=wire -->
**Say:** Kavach does not have to own the sandbox. NVIDIA's OpenShell, now a CNCF project, runs the agent with
Landlock, seccomp and a supervisor that checks every outbound connection. `kavach openshell compile` turns
the same policy file into an OpenShell policy whose only allowed destination is the Kavach gateway.

**Point at** the blue rows in the wire log: OpenShell's own audit events, in the same timeline. The raw-socket
attempt shows up as a denied connection. OpenShell does the isolation, Kavach adds the part it does not have:
card tokenization and the per-request ledger.

**Say:** This run is a replay: the Kavach half is the real gateway code, the OpenShell log is modelled on a live run, and the
badge says so. On the homelab, where OpenShell is installed, the next step runs it live.

## Live on OpenShell
<!-- action: openshell ticket=5 model=mock view=wire -->
**Say:** Same thing, for real: `openshell sandbox create` with the compiled policy, the agent as the sandbox's main
process, and OpenShell's logs tailed into the wire log.

## Policy hygiene, borrowed from Kyverno
<!-- show: ticket=2 -->
**Say:** Kyverno solved policy management for Kubernetes, and four of its ideas fit here unchanged: audit versus
enforce modes, exceptions with an owner and an expiry, a report for every decision, and linting policy in CI.

**Point at** `kavach policy lint`, `kavach policy report`, and the `exceptions:` block in the policy file.

## The eval gate
<!-- action: eval -->
**Say:** One run proves nothing, so `kavach eval` replays ten attacks, uncontained and contained:
hidden POSTs, HTTPS, query strings, raw sockets, look-alike hosts, stolen API keys, echoing the
card back.

**Point at** the table: without Kavach, every attack leaks or exposes the card; with it, all ten
are clean and every refund still succeeds. This is the check a CI pipeline would block a release on.

## The ask
<!-- show: ticket=2 -->
**Say:** One config file and one command give a small team the containment big companies build
with platform teams, on the sandbox they already choose. We are looking for design partners in healthcare, education and payments.

**Say:** Thank you.
