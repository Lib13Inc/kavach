"""Run one fake service over HTTP (and a raw TCP sink for the attacker).

    python services/server.py tickets|payments|attacker
"""
import json
import os
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic import World  # noqa: E402

ROLE = sys.argv[1] if len(sys.argv) > 1 else "tickets"
WORLD = World()
LOG = os.environ.get("ATTACKER_LOG", "/trace/attacker.jsonl")


def record(entry: dict) -> None:
    entry = {"ts": round(time.time(), 3), "source": "attacker", "kind": "attacker_received", **entry}
    print("ATTACKER RECEIVED:", json.dumps(entry), flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


class H(BaseHTTPRequestHandler):
    def _handle(self, method: str) -> None:
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        fn = getattr(WORLD, ROLE)
        status, text = fn(method, self.path, body)
        if ROLE == "attacker":
            record({"channel": "http", "method": method, "path": self.path, "body": body})
        if ROLE == "attacker" and self.path == "/log":
            status, text = 200, json.dumps(WORLD.attacker_log)
        data = text.encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._handle("GET")

    def do_POST(self):  # noqa: N802
        self._handle("POST")

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{ROLE}] " + fmt % args + "\n")


class RawSink(socketserver.BaseRequestHandler):
    def handle(self):
        data = self.request.recv(4096).decode("utf-8", "replace")
        WORLD.attacker("RAW", "", data, channel="tcp")
        record({"channel": "tcp", "method": "RAW", "path": "", "body": data})


if __name__ == "__main__":
    if ROLE == "attacker":
        srv = socketserver.ThreadingTCPServer(("0.0.0.0", 9999), RawSink)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"{ROLE} listening on :8000", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
