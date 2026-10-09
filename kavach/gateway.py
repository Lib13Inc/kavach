"""Gateway core: pure-Python policy decisions, independent of the proxy.

The mitmproxy add-on (mitm_addon.py) and the in-process test network
(evals) both call this, so what the evals prove is what the proxy runs.
"""
from __future__ import annotations

import calendar
import os
import time
from dataclasses import dataclass, field

from . import wire
from .trace import Trace
from .vault import Vault, find_pans


def load_policy(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml  # PyYAML

        return yaml.safe_load(text)
    except ImportError:  # the mitmproxy image ships ruamel.yaml instead
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(text)


def _epoch(value) -> float:
    """An exception's `expires`: epoch seconds, or an ISO date/time (UTC)."""
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "timetuple"):  # YAML parses bare dates and timestamps
        return float(calendar.timegm(value.timetuple()))
    text = str(value).rstrip("Z").replace("T", " ")
    fmt = "%Y-%m-%d %H:%M:%S" if " " in text else "%Y-%m-%d"
    return float(calendar.timegm(time.strptime(text, fmt)))


@dataclass
class Decision:
    allow: bool
    url: str = ""
    body: str = ""
    headers: dict = field(default_factory=dict)
    reason: str = ""
    rule: str = ""                 # which policy rule decided: egress.allow_hosts, secrets.X, ...
    rewrites: list = field(default_factory=list)   # what Kavach changed on the way out
    audited: bool = False          # egress.mode: audit let through something enforce would block


class Gateway:
    def __init__(self, policy: dict, vault: Vault | None = None,
                 trace: Trace | None = None, env: dict | None = None,
                 wire_log: Trace | None = None) -> None:
        self.policy = policy
        self.vault = vault or Vault()
        self.trace = trace or Trace(source="gateway")
        self.wire_log = wire_log or Trace(source="wire")
        self.env = env if env is not None else dict(os.environ)
        eg = policy.get("egress", {})
        chd = policy.get("cardholder_data", {})
        self.allow_hosts = set(eg.get("allow_hosts", []))
        self.tok_resp_from = set(chd.get("tokenize_responses_from", []))
        self.tok_req_to = set(chd.get("tokenize_requests_to", []))
        self.release_to = set(chd.get("release_to", []))
        self.secrets = policy.get("secrets", {}) or {}
        # Kyverno-style validationAction: enforce blocks; audit records the violation and lets it through.
        self.mode = str(eg.get("mode", "enforce")).lower()
        if self.mode not in ("enforce", "audit"):
            raise ValueError(f"egress.mode must be enforce or audit, got {self.mode!r}")
        self.exceptions = policy.get("exceptions", []) or []

    @classmethod
    def from_env(cls) -> "Gateway":
        policy = load_policy(os.environ.get("KAVACH_POLICY", "policy/payments.yaml"))
        tpath = os.environ.get("KAVACH_TRACE", "trace/gateway.jsonl")
        wpath = os.environ.get("KAVACH_WIRE", os.path.join(os.path.dirname(tpath) or ".", "wire.jsonl"))
        return cls(policy, trace=Trace(tpath, source="gateway"), wire_log=Trace(wpath, source="wire"))

    def _exception_for(self, host: str, now: float | None = None) -> dict | None:
        """A PolicyException-style waiver: named hosts, an owner, a reason, an expiry. Egress only;
        a stand-in key sent to the wrong host is never waivable."""
        now = time.time() if now is None else now
        for ex in self.exceptions:
            if host in ex.get("hosts", []) and (ex.get("expires") is None or _epoch(ex["expires"]) > now):
                return ex
        return None

    # ---- requests leaving the sandbox ------------------------------------
    def on_request(self, method: str, host: str, url: str, headers: dict, body: str) -> Decision:
        host = host.lower().rstrip(".")
        headers = dict(headers)
        changed: dict = {}  # only headers we rewrote; never echo stale ones (e.g. content-length)
        rewrites: list[str] = []

        # 1. Secret stand-ins: swap for the right host, block for the wrong one.
        for name, rule in self.secrets.items():
            standin = rule.get("standin", "")
            if not standin:
                continue
            hit = [k for k, v in headers.items() if standin in str(v)]
            in_body = standin in body or standin in url
            if not hit and not in_body:
                continue
            if host in set(rule.get("release_to", [])) and not in_body:
                real = self.env.get(name, "")
                for k in hit:
                    changed[k] = str(headers[k]).replace(standin, real)
                rewrites.append(f"stand-in key → real {name}")
                self.trace.emit("secret_swap", host=host, secret=name,
                                detail=f"stand-in for {name} swapped for real key (value redacted)")
            else:
                self.trace.emit("secret_misuse_blocked", host=host, secret=name,
                                detail=f"stand-in for {name} sent to {host}; request blocked")
                return Decision(False, reason=f"secret {name} may not go to {host}",
                                rule=f"secrets.{name}.release_to")

        # 2. Egress allowlist (exact host match), with Kyverno-style audit mode and exceptions.
        audited = False
        rule_name = "egress.allow_hosts"
        if host not in self.allow_hosts:
            carried = "token" if self.vault.has_token(body + url) else None
            ex = self._exception_for(host)
            if ex:
                rule_name = f"exceptions.{ex.get('name', host)}"
                self.trace.emit("policy_exception_used", host=host, exception=ex.get("name", ""),
                                owner=ex.get("owner", ""), carried=carried,
                                detail=f"{host} is off the allowlist but waived: {ex.get('reason', 'no reason given')}")
            elif self.mode == "audit":
                audited = True
                self.trace.emit("egress_audit", host=host, method=method, url=url, carried=carried,
                                detail=f"{method} {host} violates the allowlist; mode is audit, so it was let through")
            else:
                self.trace.emit("egress_blocked", host=host, method=method, url=url,
                                carried=carried, detail=f"{method} {host} is not on the allowlist")
                return Decision(False, reason=f"{host} not in egress allowlist", rule="egress.allow_hosts")

        # 3. Cardholder data.
        if host in self.release_to:
            url, n1 = self.vault.detokenize(url)
            body, n2 = self.vault.detokenize(body)
            if n1 + n2:
                rewrites.append(f"{n1 + n2} card token(s) → real card")
                self.trace.emit("token_swap", host=host, count=n1 + n2,
                                detail=f"{n1 + n2} card token(s) swapped for real PAN on the way to {host} (value redacted)")
        elif host in self.tok_req_to:
            body, n = self.vault.tokenize(body)
            if n:
                rewrites.append(f"{n} card number(s) → token")
                self.trace.emit("tokenized_request", host=host, count=n,
                                detail=f"{n} PAN(s) tokenized before reaching model provider {host}")

        if not audited:
            self.trace.emit("egress_allowed", host=host, method=method, url=_redact(url))
        return Decision(True, url=url, body=body, headers=changed, rule=rule_name,
                        rewrites=rewrites, audited=audited)

    # ---- responses coming back into the sandbox --------------------------
    def on_response(self, host: str, body: str) -> str:
        host = host.lower().rstrip(".")
        if host in self.tok_resp_from or host in self.release_to:
            body, n = self.vault.tokenize(body)
            if n:
                self.trace.emit("tokenized_response", host=host, count=n,
                                detail=f"{n} PAN(s) from {host} replaced with tokens before the agent sees them")
        return body

    # ---- wire log: every exchange, both views ----------------------------
    def record_wire(self, method: str, host: str, req_url: str, req_headers: dict, req_body: str,
                    d: Decision, *, status: int | None = None, upstream_reply: str | None = None,
                    agent_reply: str | None = None, ms: float | None = None) -> dict:
        decision = ("blocked" if not d.allow else "audit" if d.audited
                    else "rewritten" if d.rewrites else "allowed")
        rec = wire.build(
            method, req_url, host.lower().rstrip("."), decision=decision,
            reason=d.reason, rule=d.rule, agent_headers=req_headers, agent_body=req_body,
            out_headers=d.headers, out_body=d.body if d.allow else None, status=status,
            resp_upstream=upstream_reply, resp_agent=agent_reply, ms=ms, rewrites=d.rewrites,
            env=self.env, secret_names=list(self.secrets))
        return self.wire_log.emit("exchange", **rec)


def _redact(text: str) -> str:
    for p in find_pans(text):
        text = text.replace(p, "[PAN]")
    return text
