"""Append-only JSONL trace. One event per line; the trace view merges files."""
from __future__ import annotations

import json
import os
import sys
import threading
import time


class Trace:
    def __init__(self, path: str | None = None, source: str = "kavach") -> None:
        self.path = path
        self.source = source
        self.events: list[dict] = []
        self.pace = 0.0  # seconds to pause after each event; lets a local replay play out on stage
        self._lock = threading.Lock()
        if path and path != "-":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def emit(self, kind: str, **fields) -> dict:
        ev = {"ts": round(time.time(), 3), "source": self.source, "kind": kind, **fields}
        with self._lock:
            self.events.append(ev)
            if self.path == "-":  # sandbox with no shared volume: the launcher reads these off stdout
                print("@@kavach " + json.dumps(ev), flush=True)
            elif self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev) + "\n")
        if self.pace:
            time.sleep(self.pace)
        return ev

    def kinds(self) -> list[str]:
        return [e["kind"] for e in self.events]
