"""Policy-as-code hygiene, borrowed from Kyverno.

  lint()           static checks on a policy pack (what policy/lint/*.kyverno.yaml says in CEL,
                   so CI works without the Kyverno CLI)
  policy_report()  a trace -> a PolicyReport-shaped document (wgpolicyk8s.io/v1alpha2), one result
                   per decision, so existing Kyverno/Policy Reporter tooling can read Kavach output
"""
from __future__ import annotations

import time

STANDIN_PREFIX = "sk-kavach-standin-"
MAX_EXCEPTION_DAYS = 30


def _hosts(pack: dict, items: list) -> list[str]:
    """Expand "@group" references (used by draft packs such as healthcare-mh)."""
    groups = pack.get("hosts", {}) or {}
    out: list[str] = []
    for h in items or []:
        out += groups.get(h[1:], []) if str(h).startswith("@") else [h]
    return out


def lint(pack: dict, now: float | None = None) -> list[dict]:
    """Return findings [{rule, severity, message}]. severity "error" fails CI; "warn" does not."""
    from .gateway import _epoch

    now = time.time() if now is None else now
    f: list[dict] = []

    def add(rule: str, severity: str, msg: str) -> None:
        f.append({"rule": rule, "severity": severity, "message": msg})

    eg = pack.get("egress", {}) or {}
    allow = _hosts(pack, eg.get("allow_hosts", []))
    for h in allow:
        if "*" in h:
            add("no-wildcard-egress", "error", f"egress.allow_hosts has wildcard {h!r}; list hosts exactly")
    if str(eg.get("mode", "enforce")).lower() != "enforce":
        add("enforce-mode", "warn", "egress.mode is audit: violations are logged but let through")

    for name, s in (pack.get("secrets") or {}).items():
        if not str(s.get("standin", "")).startswith(STANDIN_PREFIX):
            add("standin-prefix", "error", f"secrets.{name}.standin must start with {STANDIN_PREFIX}")
        rel = _hosts(pack, s.get("release_to", []))
        if not rel:
            add("secret-has-destination", "error", f"secrets.{name}.release_to is empty")
        for h in rel:
            if h not in allow:
                add("release-within-egress", "error", f"secrets.{name} releases to {h}, which egress does not allow")

    chd = pack.get("cardholder_data", {}) or {}
    for h in chd.get("release_to", []):
        if h not in allow:
            add("release-within-egress", "error", f"cardholder_data.release_to has {h}, which egress does not allow")

    for i, ex in enumerate(pack.get("exceptions", []) or []):
        who = ex.get("name", f"#{i}")
        for need in ("owner", "reason", "expires", "hosts"):
            if not ex.get(need):
                add("exception-complete", "error", f"exception {who} is missing {need}")
        if ex.get("expires"):
            try:
                exp = _epoch(ex["expires"])
            except ValueError:
                add("exception-complete", "error", f"exception {who}: unreadable expires {ex['expires']!r}")
                continue
            if exp <= now:
                add("exception-expired", "warn", f"exception {who} has expired and no longer applies")
            elif exp - now > MAX_EXCEPTION_DAYS * 86400:
                add("exception-short-lived", "error", f"exception {who} lasts more than {MAX_EXCEPTION_DAYS} days")
    return f


# trace kind -> (rule, result, severity, message)
_RULES = {
    "egress_allowed":        ("egress.allow_hosts",      "pass", "info"),
    "egress_blocked":        ("egress.allow_hosts",      "fail", "high"),
    "egress_audit":          ("egress.allow_hosts",      "fail", "medium"),
    "policy_exception_used": ("exceptions",              "skip", "low"),
    "secret_misuse_blocked": ("secrets.release_to",      "fail", "critical"),
    "secret_swap":           ("secrets.release_to",      "pass", "info"),
    "token_swap":            ("cardholder_data.release_to", "pass", "info"),
    "tokenized_request":     ("cardholder_data.tokenize_requests_to", "pass", "info"),
    "tokenized_response":    ("cardholder_data.tokenize_responses_from", "pass", "info"),
    "ebpf_connect_denied":   ("sandbox.network",         "fail", "critical"),
}


def policy_report(events: list[dict], policy: str, namespace: str = "kavach") -> dict:
    results = []
    for e in events:
        if e.get("kind") in _RULES:
            rule, result, sev = _RULES[e["kind"]]
            src = e.get("source", "kavach")
        elif e.get("kind") == "ocsf" and e.get("verdict") in ("denied", "blocked"):
            rule, result, sev, src = "sandbox.network", "fail", "high", "openshell"
        else:
            continue
        host = e.get("host") or e.get("dest_host") or ""
        results.append({
            "policy": policy, "rule": rule, "result": result, "severity": sev, "source": src,
            "message": e.get("detail") or e.get("reason") or e.get("raw") or e["kind"],
            "timestamp": {"seconds": int(e.get("ts", time.time())), "nanos": 0},
            "properties": {k: str(v) for k, v in (("host", host), ("kind", e["kind"]),
                                                  ("exception", e.get("exception")), ("owner", e.get("owner"))) if v},
        })
    summary = {k: sum(1 for r in results if r["result"] == k) for k in ("pass", "fail", "warn", "error", "skip")}
    return {"apiVersion": "wgpolicyk8s.io/v1alpha2", "kind": "PolicyReport",
            "metadata": {"name": f"kavach-{policy}".replace("@", "-"), "namespace": namespace},
            "scope": {"kind": "Pack", "name": policy}, "summary": summary, "results": results}

