#!/usr/bin/env python3
"""Stage demo server: runs the demo steps and streams the merged trace to the browser.

    python3 demo/server.py [--port 8088]

Serves the stage UI at /, the old trace viewer at /trace-view/, and a small JSON API:

    GET  /api/script           SCRIPT.md parsed into steps, plus the models this host can run
    GET  /api/tickets          the support tickets
    POST /api/run              {"kind": "uncontained"|"contained"|"eval", "ticket": "2", "model": "mock"|"openai"|"crusoe"|...}
    GET  /api/events?since=N   the current run and its events after index N

Only those three run kinds, known ticket ids and the models set up in this host's .env are accepted: the page
never gets to choose a command. Standard library only, so it runs on the host's python3.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "demo")
TRACE = os.path.join(ROOT, "trace")
TICKETS = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "services", "tickets.json")))}
TRACE_FILES = ["agent.jsonl", "agent-naked.jsonl", "gateway.jsonl", "attacker.jsonl", "ebpf.jsonl"]
NOISE = re.compile(r"^\s*(Container \S+ (Creating|Created|Starting|Started|Running|Waiting|Healthy)|\[\+\]|time=)")



def host_models() -> dict[str, str]:
    """Models this host can run, with display labels, from its .env (never served)."""
    env: dict[str, str] = {}
    try:
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            k, sep, v = line.strip().partition("=")
            if sep and not k.startswith("#"):
                env[k.strip()] = v.split(" #")[0].strip()
    except FileNotFoundError:
        pass
    models = {"mock": "mock (always obeys)"}
    base = env.get("OPENAI_BASE_URL", "")
    if base and (env.get("OPENAI_API_KEY") or "api.openai.com" not in base):
        models["openai"] = env.get("OPENAI_MODEL") or "OpenAI-compatible"
    if env.get("CRUSOE_API_KEY"):
        models["crusoe"] = (env.get("CRUSOE_MODEL") or "Qwen/Qwen3.8-27B") + " · Crusoe"
    if env.get("ANTHROPIC_API_KEY"):
        models["anthropic"] = env.get("ANTHROPIC_MODEL") or "Claude"
    return models


LOCK = threading.Lock()
RUN: dict = {"id": 0, "status": "idle", "events": []}


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
def _add(ev: dict) -> None:
    with LOCK:
        ev.setdefault("ts", round(time.time(), 3))
        ev["i"] = len(RUN["events"])
        RUN["events"].append(ev)


def _command(kind: str, ticket: str, model: str) -> list[str]:
    if kind == "eval":
        py = os.path.join(ROOT, ".venv", "bin", "python")
        return [py if os.path.exists(py) else "python3", "-m", "kavach.cli", "eval"]
    profile, svc = ("uncontained", "agent-naked") if kind == "uncontained" else ("contained", "agent")
    return ["docker", "compose", "--profile", profile, "run", "--rm", "-T", svc,
            "python", "agent/agent.py", "--ticket", ticket, "--model", model]


def _tail(run_id: int, stop: threading.Event) -> None:
    """Follow the trace files the containers write and add their events to the run."""
    offsets: dict[str, int] = {}
    while True:
        done = stop.is_set()
        for name in TRACE_FILES:
            path = os.path.join(TRACE, name)
            try:
                with open(path, encoding="utf-8") as f:
                    f.seek(offsets.get(name, 0))
                    chunk = f.read()
                    # Only consume whole lines; a writer may be mid-line.
                    cut = chunk.rfind("\n") + 1
                    offsets[name] = offsets.get(name, 0) + len(chunk[:cut].encode())
            except FileNotFoundError:
                continue
            for line in chunk[:cut].splitlines():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if RUN["id"] != run_id:
                    return
                ev["file"] = name.removesuffix(".jsonl")
                _add(ev)
        if done:
            return
        time.sleep(0.15)


def _run(run_id: int, kind: str, ticket: str, model: str) -> None:
    for name in TRACE_FILES:
        try:
            os.remove(os.path.join(TRACE, name))
        except FileNotFoundError:
            pass
    stop = threading.Event()
    tailer = threading.Thread(target=_tail, args=(run_id, stop), daemon=True)
    tailer.start()

    guard = None
    if kind == "contained":
        # The host-side eBPF guard attaches to the agent container as soon as it appears.
        guard = subprocess.Popen(["sudo", "-n", os.path.join(ROOT, "ebpf", "guard.sh")], cwd=ROOT,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _add({"source": "demo", "kind": "guard_armed", "detail": "eBPF guard waiting for the agent container"})

    cmd = _command(kind, ticket, model)
    _add({"source": "demo", "kind": "command", "detail": " ".join(cmd[:4] + ["…"] + cmd[-4:]) if kind != "eval" else "kavach eval"})
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        line = line.rstrip()
        if line and not NOISE.search(line):
            _add({"source": "console", "kind": "output", "text": line})
    code = proc.wait()

    if guard:
        time.sleep(0.8)
        subprocess.run(["sudo", "-n", "pkill", "-x", "bpftrace"], check=False)
        guard.wait(timeout=5)
    time.sleep(0.6)  # let the last trace lines land
    stop.set()
    tailer.join(timeout=3)
    with LOCK:
        RUN.update(status="done", exit=code, ended=time.time())


def start_run(kind: str, ticket: str, model: str) -> tuple[int, dict]:
    if kind not in {"uncontained", "contained", "eval"}:
        return 400, {"error": "kind must be uncontained, contained or eval"}
    if kind != "eval" and ticket not in TICKETS:
        return 400, {"error": f"unknown ticket {ticket}"}
    models = host_models()
    if model not in models:
        return 400, {"error": f"model {model} is not set up on this host (available: {', '.join(models)})"}
    if kind == "uncontained" and model == "crusoe":
        # The uncontained agent never gets the real Crusoe key: it is the one the attack succeeds against.
        return 400, {"error": "crusoe runs only inside Kavach; the uncontained agent never gets the real key"}
    with LOCK:
        if RUN["status"] == "running":
            return 409, {"error": "a run is already in progress"}
        run_id = RUN["id"] + 1
        RUN.clear()
        RUN.update(id=run_id, status="running", kind=kind, ticket=ticket, model=model,
                   started=time.time(), events=[])
    threading.Thread(target=_run, args=(run_id, kind, ticket, model), daemon=True).start()
    return 200, {"id": run_id}


# ---------------------------------------------------------------------------
# Script: SCRIPT.md -> steps
# ---------------------------------------------------------------------------
def parse_script() -> dict:
    text = open(os.path.join(HERE, "SCRIPT.md"), encoding="utf-8").read()
    parts = re.split(r"^## ", text, flags=re.M)
    intro, steps = parts[0], []
    for part in parts[1:]:
        title, _, body = part.partition("\n")
        action = None
        m = re.search(r"<!--\s*action:\s*(.+?)\s*-->", body)
        if m:
            words = m.group(1).split()
            action = {"kind": words[0], **dict(w.split("=", 1) for w in words[1:])}
            body = body.replace(m.group(0), "")
        m = re.search(r"<!--\s*show:\s*ticket=(\w+)\s*-->", body)
        show = m.group(1) if m else (action or {}).get("ticket")
        if m:
            body = body.replace(m.group(0), "")
        steps.append({"title": title.strip(), "notes": body.strip(), "action": action, "ticket": show})
    title = re.search(r"^# (.+)$", intro, re.M)
    return {"title": title.group(1) if title else "Kavach demo", "steps": steps, "models": host_models()}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def _json(self, status: int, obj) -> None:
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        if u.path == "/api/script":
            return self._json(200, parse_script())
        if u.path == "/api/tickets":
            return self._json(200, list(TICKETS.values()))
        if u.path == "/api/events":
            since = int(parse_qs(u.query).get("since", ["0"])[0] or 0)
            with LOCK:
                run = {k: v for k, v in RUN.items() if k != "events"}
                events = RUN["events"][since:]
            return self._json(200, {"run": run, "events": events})
        if u.path in ("/", "/index.html"):
            self.path = "/demo/static/index.html"
        elif not (u.path.startswith(("/demo/static/", "/trace-view/", "/trace/"))):
            return self._json(404, {"error": "not found"})
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path != "/api/run":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json(400, {"error": "body must be JSON"})
        status, obj = start_run(str(body.get("kind", "")), str(body.get("ticket", "2")),
                                str(body.get("model", "mock")))
        return self._json(status, obj)

    def end_headers(self):
        if self.path.startswith("/demo/static/"):
            self.send_header("cache-control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/api/events" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    print(f"kavach demo on http://{a.host}:{a.port}/", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
