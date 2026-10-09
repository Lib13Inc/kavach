"""NVIDIA OpenShell as a Kavach sandbox base.

OpenShell (https://github.com/NVIDIA/OpenShell, a CNCF project) runs an agent in a sandbox
with Landlock + seccomp + a supervisor that mediates every outbound connection against a
YAML policy. Kavach brings the data layer OpenShell does not have: PAN tokenization, a
per-session wire ledger, evals, vertical packs. This module is the glue:

  compile_policy()   Kavach pack  ->  OpenShell policy (version: 1)
  validate()         the documented schema rules, so a bad policy fails before `sandbox create`
  parse_line()       OpenShell OCSF log lines (shorthand and JSONL)  ->  Kavach trace events
  follow()/replay()  feed those events into trace/openshell.jsonl for the demo UI

Everything here is built from the public docs (docs.nvidia.com/openshell). It has not been
run against a live OpenShell yet; see docs/openshell.md for what is assumed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from typing import Iterable, Iterator

from .trace import Trace

DEFAULT_BINARY = "/usr/local/bin/python3.12"      # python:3.12-slim, see sandbox/Dockerfile
DEFAULT_GATEWAY_HOST = "host.openshell.internal"   # ASSUMED: docs don't name the host alias; override with --gateway-host
PROXY_PORT = 8080
TOP_LEVEL = {"version", "filesystem_policy", "landlock", "process", "network_policies", "network_middlewares"}


# ---------------------------------------------------------------------------
# Policy: Kavach pack -> OpenShell policy
# ---------------------------------------------------------------------------
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _port(host: str, ports: dict) -> int:
    return int(ports.get(host, 80 if host.endswith(".internal") else 443))


def compile_policy(pack: dict, mode: str = "gateway", gateway_host: str = DEFAULT_GATEWAY_HOST,
                   binary: str = DEFAULT_BINARY, middleware: bool = False,
                   run_as: str | None = None) -> tuple[dict, list[str]]:
    """Return (openshell_policy, warnings).

    mode="gateway": OpenShell fences the sandbox so the only reachable thing is the Kavach gateway,
        which keeps doing allowlist, token swap, key swap and the wire log. This replaces the Docker
        internal network and the eBPF guard; OpenShell's own logs record any attempt to go around.
    mode="native": OpenShell enforces the allowlist itself, per host, at L7, with its own credential
        providers. Kavach's tokenization has no OpenShell equivalent, so it needs `middleware=True`
        and a Kavach middleware service registered on the OpenShell gateway.
    """
    warnings: list[str] = []
    eg = pack.get("egress", {})
    os_cfg = pack.get("openshell", {}) or {}
    ports = os_cfg.get("ports", {}) or {}
    enforcement = "audit" if str(eg.get("mode", "enforce")).lower() == "audit" else "enforce"

    pol: dict = {
        "version": 1,
        "filesystem_policy": {
            "include_workdir": True,   # OpenShell validates the image workdir is writable by the agent
            "read_only": ["/usr", "/lib", "/lib64", "/etc"],
            "read_write": ["/tmp", "/trace"],
        },
        "landlock": {"compatibility": "hard_requirement"},
        "network_policies": {},
    }
    if run_as:  # otherwise OpenShell uses the image's USER; a named user must exist in the image (it checks)
        pol["process"] = {"run_as_user": run_as, "run_as_group": run_as}
    nets = pol["network_policies"]

    if mode == "gateway":
        nets["kavach_gateway"] = {
            "name": "Kavach gateway (the only way out)",
            "endpoints": [{"host": gateway_host, "port": int(pack.get("sandbox", {}).get("proxy_port", PROXY_PORT)),
                           "protocol": "tcp",
                           # Found live: without this OpenShell inspects the HTTP inside the tunnel and rejects
                           # forward-proxy requests (request_authority_mismatch). The Kavach gateway is the inspector.
                           "tls": "skip"}],
            "binaries": [{"path": binary}],
        }
    elif mode == "native":
        providers = {name: _slug(name) for name in (pack.get("secrets") or {})}
        for host in sorted(eg.get("allow_hosts", [])):
            ep: dict = {"host": host, "port": _port(host, ports), "protocol": "rest",
                        "enforcement": enforcement, "access": "read-write"}
            for sname, rule in (pack.get("secrets") or {}).items():
                if host in rule.get("release_to", []):
                    ep["credential_binding"] = {"provider": providers[sname]}
            nets[_slug(host)] = {"name": host, "endpoints": [ep], "binaries": [{"path": binary}]}
        if middleware:
            hosts = sorted(set(pack.get("cardholder_data", {}).get("tokenize_requests_to", [])
                               + pack.get("cardholder_data", {}).get("tokenize_responses_from", [])))
            if hosts:
                pol["network_middlewares"] = {"kavach_vault": {
                    "middleware": "kavach-vault", "order": 10, "on_error": "fail_closed",
                    "endpoints": {"include": hosts}}}
        elif pack.get("cardholder_data"):
            warnings.append("native mode without --middleware: card numbers are NOT tokenized. "
                            "OpenShell has no PAN vault; use gateway mode or register a kavach-vault middleware.")
        if pack.get("secrets"):
            warnings.append("native mode: create one OpenShell provider per secret ("
                            + ", ".join(sorted(providers.values())) + ") holding the real key; the agent never sees it.")
    else:
        raise ValueError("mode must be gateway or native")

    if pack.get("exceptions"):
        warnings.append("exceptions are enforced by the Kavach gateway only; they are not compiled into the OpenShell policy.")
    for host in eg.get("allow_hosts", []):
        if "*" in host and host.count(".") < 2:
            warnings.append(f"wildcard host {host!r} needs at least three DNS labels in OpenShell")
    return pol, warnings


def render(pol: dict, header: str = "") -> str:
    import yaml

    body = yaml.safe_dump(pol, sort_keys=False, default_flow_style=False)
    return (header.rstrip() + "\n" if header else "") + body


# ---------------------------------------------------------------------------
# Validation: the rules the docs state, so mistakes surface before `sandbox create`
# ---------------------------------------------------------------------------
HOST_RE = re.compile(r"^(\*\*\.)?[A-Za-z0-9*_-]+(\.[A-Za-z0-9*_-]+)*$")


def validate(pol: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(pol, dict):
        return ["policy must be a mapping"]
    if pol.get("version") != 1:
        errs.append("version must be 1")
    for k in pol:
        if k not in TOP_LEVEL:
            errs.append(f"unknown top-level field {k!r} (OpenShell rejects unknown fields)")
    fs = pol.get("filesystem_policy", {}) or {}
    for key in ("read_only", "read_write"):
        for p in fs.get(key, []) or []:
            if not str(p).startswith("/") or ".." in str(p).split("/") or len(str(p).encode()) > 4096:
                errs.append(f"filesystem_policy.{key}: {p!r} must be absolute, without .., at most 4096 bytes")
    if "/" in (fs.get("read_write") or []):
        errs.append("filesystem_policy.read_write cannot contain /")
    if len(fs.get("read_write") or []) > 256:
        errs.append("filesystem_policy.read_write allows at most 256 paths")
    if (pol.get("landlock") or {}).get("compatibility", "best_effort") not in ("best_effort", "hard_requirement"):
        errs.append("landlock.compatibility must be best_effort or hard_requirement")
    for f in ("run_as_user", "run_as_group"):
        v = str((pol.get("process") or {}).get(f, "sandbox"))
        if v != "sandbox" and not (v.isdigit() and 1 <= int(v) <= 4294967294):
            errs.append(f"process.{f} must be 'sandbox' or a numeric id between 1 and 4294967294 (root is rejected)")
    for name, rule in (pol.get("network_policies") or {}).items():
        where = f"network_policies.{name}"
        if name.startswith("_provider_"):
            errs.append(f"{where}: keys cannot start with _provider_")
        if not rule.get("binaries"):
            errs.append(f"{where}: binaries is empty, so the rule matches nothing")
        for ep in rule.get("endpoints", []) or []:
            errs += _validate_endpoint(where, ep)
    mws = pol.get("network_middlewares") or {}
    if len(mws) > 10:
        errs.append("network_middlewares allows at most 10 entries")
    for name, mw in mws.items():
        if not mw.get("middleware") or not (mw.get("endpoints") or {}).get("include"):
            errs.append(f"network_middlewares.{name}: middleware and endpoints.include are required")
    return errs


def _validate_endpoint(where: str, ep: dict) -> list[str]:
    errs: list[str] = []
    host = ep.get("host")
    if host is None and not ep.get("allowed_ips"):
        errs.append(f"{where}: an endpoint without host needs allowed_ips")
    if host is not None:
        if not HOST_RE.match(host):
            errs.append(f"{where}: bad host {host!r}")
        if "*" in host and len(host.split(".")) < 3:
            errs.append(f"{where}: wildcard host {host!r} needs at least three DNS labels")
        if "**" in host and not host.startswith("**."):
            errs.append(f"{where}: ** works only as the whole first label ({host!r})")
    if "port" in ep and "ports" in ep:
        errs.append(f"{where}: use port or ports, not both")
    ports = [ep["port"]] if "port" in ep else list(ep.get("ports", []))
    for p in ports:
        if p in (2379, 2380, 6443, 10250, 10255):
            errs.append(f"{where}: port {p} is always blocked")
    proto = ep.get("protocol")
    if proto not in (None, "rest", "websocket", "graphql", "mcp", "json-rpc", "tcp"):
        errs.append(f"{where}: unknown protocol {proto!r}")
    if ep.get("enforcement", "audit") not in ("audit", "enforce"):
        errs.append(f"{where}: enforcement must be audit or enforce")
    if ep.get("access") not in (None, "read-only", "read-write", "full"):
        errs.append(f"{where}: access must be read-only, read-write or full")
    if ep.get("access") and ep.get("rules"):
        errs.append(f"{where}: access and rules cannot be combined")
    if proto in ("rest", "websocket", "graphql") and not (ep.get("access") or ep.get("rules")):
        errs.append(f"{where}: protocol {proto} needs access or rules")
    if proto in ("mcp", "json-rpc") and not ep.get("rules"):
        errs.append(f"{where}: protocol {proto} needs rules")
    if ep.get("deny_rules") and not proto:
        errs.append(f"{where}: deny_rules require protocol")
    if proto == "tcp":
        if host is None or not ports:
            errs.append(f"{where}: protocol tcp needs a host and a port")
        if any(k in ep for k in ("rules", "deny_rules", "access")):
            errs.append(f"{where}: protocol tcp accepts no request-level fields")
    return errs


# ---------------------------------------------------------------------------
# Logs: OpenShell OCSF -> Kavach trace events
# ---------------------------------------------------------------------------
LINE_RE = re.compile(
    r"^(?:\[(?P<ts>\d+(?:\.\d+)?)\]\s+\[(?P<src>[\w-]+)\]\s+\[(?P<lvl>[A-Za-z ]+?)\]\s+\[(?P<tgt>[\w:.-]+)\]\s+"
    r"|(?P<iso>\d{4}-\d\d-\d\dT[\d:.]+Z)\s+)?"
    r"(?:OCSF\s+)?(?P<cls>[A-Z]+):(?P<act>[A-Z_]+)\s+\[(?P<sev>[A-Z]+)\]\s*(?P<verdict>ALLOWED|DENIED|BLOCKED)?\s*(?P<rest>.*)$")
CTX_RE = re.compile(r"\[([^\]]*)\]")
PROC_RE = re.compile(r"(?P<proc>\S+?)\((?P<pid>\d+)\)\s*->\s*(?P<host>\S+?):(?P<port>\d+)")
HTTP_RE = re.compile(r"^(?P<method>[A-Z]+)\s+(?P<url>\S+)")
CLASS_UID = {"EVENT": 0, "NET": 4001, "HTTP": 4002, "SSH": 4007, "PROC": 1007,
             "FINDING": 2004, "CONFIG": 5019, "LIFECYCLE": 6002}
SEV_ID = {1: "INFO", 2: "LOW", 3: "MED", 4: "HIGH", 5: "CRIT", 6: "FATAL"}


def parse_line(line: str) -> dict | None:
    """One OpenShell log line -> event fields, or None if it is not an OCSF event."""
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        return _parse_json(line)
    m = LINE_RE.match(line)
    if not m:
        return None
    ev: dict = {"cls": m["cls"], "class_uid": CLASS_UID.get(m["cls"]), "act": m["act"], "sev": m["sev"],
                "verdict": (m["verdict"] or "").lower(), "raw": line}
    if m["ts"]:
        ev["ts"] = float(m["ts"])
    elif m["iso"]:  # what the supervisor prints live: 2026-10-09T21:15:32.224Z OCSF NET:OPEN ...
        import calendar
        whole, _, frac = m["iso"].rstrip("Z").partition(".")
        ev["ts"] = calendar.timegm(time.strptime(whole, "%Y-%m-%dT%H:%M:%S")) + float("0." + (frac or "0"))
    rest = m["rest"]
    head = CTX_RE.split(rest, maxsplit=1)[0].strip()
    for ctx in CTX_RE.findall(rest):
        if ctx.startswith("reason:"):
            ev["reason"] = ctx[len("reason:"):].strip()
        else:
            for k, v in re.findall(r"(\w+):(\S+)", ctx):
                ev[k] = None if v == "-" else v
    if (p := PROC_RE.search(head)):
        ev.update(proc=p["proc"], pid=int(p["pid"]), dest_host=p["host"], dest_port=int(p["port"]))
    elif (h := HTTP_RE.match(head)):
        ev.update(method=h["method"], url=h["url"])
    elif head:
        ev["message"] = head
    return ev


def _parse_json(line: str) -> dict | None:
    """OCSF JSONL, best effort: the exact field set is not in the public docs yet."""
    try:
        d = json.loads(line)
    except ValueError:
        return None
    uid = d.get("class_uid")
    if uid is None:
        return None
    cls = next((k for k, v in CLASS_UID.items() if v == uid), str(uid))
    dst = d.get("dst_endpoint") or {}
    req = d.get("http_request") or {}
    proc = d.get("process") or {}
    verdict = str(d.get("action") or d.get("disposition") or "").lower()
    ev = {"cls": cls, "class_uid": uid, "act": str(d.get("activity_name") or d.get("activity_id") or "").upper(),
          "sev": SEV_ID.get(d.get("severity_id"), str(d.get("severity") or "").upper()),
          "verdict": {"allowed": "allowed", "denied": "denied", "blocked": "blocked"}.get(verdict, verdict),
          "raw": line}
    if d.get("time"):
        t = float(d["time"])
        ev["ts"] = t / 1000 if t > 1e11 else t
    if dst.get("hostname") or dst.get("ip"):
        ev["dest_host"], ev["dest_port"] = dst.get("hostname") or dst.get("ip"), dst.get("port")
    if proc:
        ev["proc"], ev["pid"] = (proc.get("file") or {}).get("path") or proc.get("name"), proc.get("pid")
    if req:
        ev["method"] = req.get("http_method")
        ev["url"] = (req.get("url") or {}).get("url_string") or (req.get("url") or {}).get("path")
    if d.get("status_detail"):
        ev["reason"] = d["status_detail"]
    return ev


def to_event(parsed: dict, replayed: bool = False) -> dict:
    """Parsed line -> Kavach trace fields (kind 'ocsf'), keeping OpenShell's own time when present."""
    fields = {k: v for k, v in parsed.items() if v is not None and k != "ts"}
    if replayed:
        fields["replayed"] = True
    return fields


def emit(trace: Trace, parsed: dict, replayed: bool = False) -> dict:
    ev = trace.emit("ocsf", **to_event(parsed, replayed))
    return ev


def denials(events: Iterable[dict]) -> list[dict]:
    return [e for e in events if e.get("kind") == "ocsf" and e.get("verdict") in ("denied", "blocked")]


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------
def available() -> bool:
    return shutil.which("openshell") is not None


def create_command(name: str, policy_path: str, image: str | None, inner: list[str]) -> list[str]:
    """`openshell sandbox create` with a policy and the agent as the sandbox's main process."""
    cmd = ["openshell", "sandbox", "create", "--name", name, "--policy", policy_path]
    if image:
        cmd += ["--from", image]
    return cmd + ["--"] + inner


def logs_command(name: str, since: str = "10m") -> list[str]:
    return ["openshell", "logs", name, "--since", since, "--source", "sandbox"]


def follow(name: str, trace: Trace, stop=None, interval: float = 0.5) -> None:
    """Poll `openshell logs` and append new OCSF events to the trace. Polling because the CLI's
    streaming flags are not in the public docs; lines are de-duplicated by full text. The gateway only keeps
    the last 30 lines per sandbox in the CLI view, so a fast poll matters during a burst."""
    seen: set[str] = set()
    start = time.time() - 2   # a sandbox reused under the same name still has the last run's lines in its buffer
    while not (stop and stop.is_set()):
        out = subprocess.run(logs_command(name, "2m"), capture_output=True, text=True, timeout=30).stdout
        if not out:
            time.sleep(interval)
            continue
        for line in out.splitlines():
            if line in seen:
                continue
            seen.add(line)
            if (p := parse_line(line)) and p.get("ts", start) >= start:
                emit(trace, p)
        time.sleep(interval)


def read_lines(path: str) -> Iterator[str]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.lstrip().startswith("#"):
                yield line.rstrip("\n")


def replay(path: str, trace: Trace, pace: float = 0.5) -> int:
    """Play a recorded/hand-written log into the trace, flagged replayed=True so no UI mistakes it for live."""
    n = 0
    for line in read_lines(path):
        if (p := parse_line(line)):
            emit(trace, p, replayed=True)
            n += 1
            time.sleep(pace)
    return n
