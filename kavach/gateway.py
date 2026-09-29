"""Gateway core: pure-Python policy decisions, independent of the proxy.

The mitmproxy add-on (mitm_addon.py) and the in-process test network
(evals) both call this, so what the evals prove is what the proxy runs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .vault import Vault, find_pans
from .trace import Trace


def load_policy(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml  # PyYAML

        return yaml.safe_load(text)
    except ImportError:  # the mitmproxy image ships ruamel.yaml instead
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(text)


@dataclass
class Decision:
    allow: bool
    url: str = ""
    body: str = ""
    headers: dict = field(default_factory=dict)
    reason: str = ""


class Gateway:
    def __init__(self, policy: dict, vault: Vault | None = None,
                 trace: Trace | None = None, env: dict | None = None) -> None:
        self.policy = policy
        self.vault = vault or Vault()
        self.trace = trace or Trace(source="gateway")
        self.env = env if env is not None else dict(os.environ)
        eg = policy.get("egress", {})
        chd = policy.get("cardholder_data", {})
        self.allow_hosts = set(eg.get("allow_hosts", []))
        self.tok_resp_from = set(chd.get("tokenize_responses_from", []))
        self.tok_req_to = set(chd.get("tokenize_requests_to", []))
        self.release_to = set(chd.get("release_to", []))
        self.secrets = policy.get("secrets", {}) or {}

    @classmethod
    def from_env(cls) -> "Gateway":
        policy = load_policy(os.environ.get("KAVACH_POLICY", "policy/payments.yaml"))
        trace = Trace(os.environ.get("KAVACH_TRACE", "trace/gateway.jsonl"), source="gateway")
        return cls(policy, trace=trace)

    # ---- requests leaving the sandbox ------------------------------------
    def on_request(self, method: str, host: str, url: str, headers: dict, body: str) -> Decision:
        host = host.lower().rstrip(".")
        headers = dict(headers)
        changed: dict = {}  # only headers we rewrote; never echo stale ones (e.g. content-length)

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
                self.trace.emit("secret_swap", host=host, secret=name,
                                detail=f"stand-in for {name} swapped for real key (value redacted)")
            else:
                self.trace.emit("secret_misuse_blocked", host=host, secret=name,
                                detail=f"stand-in for {name} sent to {host}; request blocked")
                return Decision(False, reason=f"secret {name} may not go to {host}")

        # 2. Egress allowlist (exact host match).
        if host not in self.allow_hosts:
            carried = "token" if self.vault.has_token(body + url) else None
            self.trace.emit("egress_blocked", host=host, method=method, url=url,
                            carried=carried,
                            detail=f"{method} {host} is not on the allowlist")
            return Decision(False, reason=f"{host} not in egress allowlist")

        # 3. Cardholder data.
        if host in self.release_to:
            url, n1 = self.vault.detokenize(url)
            body, n2 = self.vault.detokenize(body)
            if n1 + n2:
                self.trace.emit("token_swap", host=host, count=n1 + n2,
                                detail=f"{n1 + n2} card token(s) swapped for real PAN on the way to {host} (value redacted)")
        elif host in self.tok_req_to:
            body, n = self.vault.tokenize(body)
            if n:
                self.trace.emit("tokenized_request", host=host, count=n,
                                detail=f"{n} PAN(s) tokenized before reaching model provider {host}")

        self.trace.emit("egress_allowed", host=host, method=method, url=_redact(url))
        return Decision(True, url=url, body=body, headers=changed)

    # ---- responses coming back into the sandbox --------------------------
    def on_response(self, host: str, body: str) -> str:
        host = host.lower().rstrip(".")
        if host in self.tok_resp_from or host in self.release_to:
            body, n = self.vault.tokenize(body)
            if n:
                self.trace.emit("tokenized_response", host=host, count=n,
                                detail=f"{n} PAN(s) from {host} replaced with tokens before the agent sees them")
        return body


def _redact(text: str) -> str:
    for p in find_pans(text):
        text = text.replace(p, "[PAN]")
    return text
