"""Append-only JSONL trace. One event per line; the trace view merges files."""
from __future__ import annotations

import json
import os
import threading
import time


class Trace:
    def __init__(self, path: str | None = None, source: str = "kavach") -> None:
        self.path = path
        self.source = source
        self.events: list[dict] = []
        self._lock = threading.Lock()
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def emit(self, kind: str, **fields) -> dict:
        ev = {"ts": round(time.time(), 3), "source": self.source, "kind": kind, **fields}
        with self._lock:
            self.events.append(ev)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev) + "\n")
        return ev

    def kinds(self) -> list[str]:
        return [e["kind"] for e in self.events]
