"""In-process network: routes the agent's traffic through the real Gateway
code to the fake services, with no Docker. Used by `kavach eval` and
`kavach demo --local`.

Contained mode mirrors the Docker setup: HTTP goes via the gateway, and the
sandbox has no route for raw sockets (in Docker, the internal network drops
them and the eBPF policy logs and kills the process).
"""
from __future__ import annotations

import json
import time
from urllib.parse import urlsplit

from .gateway import Gateway

ATTACKER_IP = "172.28.0.66"


class InProcessNet:
    def __init__(self, world, gateway: Gateway | None = None) -> None:
        self.world = world
        self.gw = gateway  # None = uncontained

    def _route(self, host: str):
        if host == "tickets.internal":
            return self.world.tickets
        if host == "payments.internal":
            return self.world.payments
        if host == "attacker.example" or host.endswith(".attacker.example") or host == ATTACKER_IP:
            return self.world.attacker
        return None

    def request(self, method: str, url: str, body: dict | None = None,
                headers: dict | None = None) -> tuple[int, str]:
        text = json.dumps(body) if body is not None else ""
        host = (urlsplit(url).hostname or "").lower()
        orig_url, orig_headers, orig_text, t0 = url, headers or {}, text, time.time()
        d = None
        if self.gw is not None:
            d = self.gw.on_request(method, host, url, orig_headers, text)
            if not d.allow:
                reply = json.dumps({"blocked_by": "kavach", "reason": d.reason})
                self.gw.record_wire(method, host, orig_url, orig_headers, orig_text, d, status=403,
                                    agent_reply=reply, ms=(time.time() - t0) * 1000)
                return 403, reply
            url, text = d.url, d.body
        handler = self._route(host)
        if handler is None:
            if d is not None:
                self.gw.record_wire(method, host, orig_url, orig_headers, orig_text, d, status=0,
                                    agent_reply=f"network error: cannot resolve {host}")
            return 0, f"network error: cannot resolve {host}"
        parts = urlsplit(url)
        path = parts.path + (("?" + parts.query) if parts.query else "")
        status, resp = handler(method, path, text)
        if self.gw is not None:
            seen = self.gw.on_response(host, resp)
            self.gw.record_wire(method, host, orig_url, orig_headers, orig_text, d, status=status,
                                upstream_reply=resp, agent_reply=seen, ms=(time.time() - t0) * 1000)
            resp = seen
        return status, resp

    def raw_send(self, host: str, port: int, data: str) -> str:
        if self.gw is not None:
            self.gw.trace.emit(
                "ebpf_connect_denied", host=host, port=port,
                detail=f"connect() to {host}:{port} outside the gateway; sandbox has no route, "
                       f"eBPF policy logs it and kills the process")
            return "socket error: [Errno 101] Network is unreachable"
        if self._route(host) is None:
            return f"socket error: cannot resolve {host}"
        self.world.attacker("RAW", "", data, channel="tcp")
        return "sent"
