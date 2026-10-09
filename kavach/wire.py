"""Wire log: one record per request that crosses the gateway.

Each record keeps two views of the same exchange so the UI can show what
Kavach changed: what the agent sent (tokens, stand-in keys) and what left the
sandbox (real values, masked here so the log itself is safe to keep and ship).
"""
from __future__ import annotations

import itertools
import re
from urllib.parse import urlsplit

from .vault import PAN_RE, luhn_ok

BODY_CAP = 4096
_ids = itertools.count(1)


def mask_pans(text: str) -> str:
    """4242 4242 4242 4242 -> 4242 42** **** 4242 (first 6, last 4, like PCI display rules)."""
    def sub(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            return digits[:6] + "*" * (len(digits) - 10) + digits[-4:]
        return m.group(0)
    return PAN_RE.sub(sub, text)


def mask_secrets(text: str, env: dict, names: list[str]) -> str:
    """Replace the gateway's real secret values with [REAL:NAME]."""
    for name in names:
        val = env.get(name, "")
        if val and val in text:
            text = text.replace(val, f"[REAL:{name}]")
    return text


def clip(text: str, cap: int = BODY_CAP) -> str:
    return text if len(text) <= cap else text[:cap] + f"… [{len(text) - cap} more bytes]"


def view_headers(headers: dict) -> dict:
    """Headers worth showing. Content framing headers are noise."""
    skip = {"content-length", "accept-encoding", "connection", "proxy-connection", "user-agent"}
    return {k.lower(): str(v) for k, v in headers.items() if k.lower() not in skip}


def build(method: str, url: str, host: str, *, decision: str, reason: str = "",
          agent_headers: dict, agent_body: str, out_headers: dict | None, out_body: str | None,
          status: int | None, resp_upstream: str | None, resp_agent: str | None,
          ms: float | None, rewrites: list[str], rule: str, env: dict, secret_names: list[str]) -> dict:
    """Build one wire record. `decision` is allowed | rewritten | blocked | audit."""
    parts = urlsplit(url)
    path = mask_pans(parts.path + (("?" + parts.query) if parts.query else ""))

    def safe(t: str | None) -> str | None:
        return None if t is None else clip(mask_secrets(mask_pans(t), env, secret_names))

    final = {**view_headers(agent_headers), **view_headers(out_headers or {})}
    return {
        "id": next(_ids), "method": method, "host": host, "path": path or "/", "scheme": parts.scheme,
        "decision": decision, "reason": reason, "rule": rule, "rewrites": rewrites,
        "status": status, "ms": None if ms is None else round(ms, 1),
        "agent_sent": {"headers": {k: mask_pans(v) for k, v in view_headers(agent_headers).items()},
                       "body": clip(mask_pans(agent_body))},
        "left_sandbox": None if decision == "blocked" else {
            "headers": {k: mask_secrets(mask_pans(v), env, secret_names) for k, v in final.items()},
            "body": safe(out_body if out_body is not None else agent_body)},
        "upstream_reply": safe(resp_upstream),
        "agent_received": clip(resp_agent) if resp_agent is not None else None,
    }
