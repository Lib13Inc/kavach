"""mitmproxy add-on: the Kavach gateway on the wire.

    mitmdump --listen-port 8080 -s kavach/mitm_addon.py

Environment: KAVACH_POLICY, KAVACH_TRACE, plus the REAL API keys
(ANTHROPIC_API_KEY, OPENAI_API_KEY). The agent container never gets those.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mitmproxy import http  # noqa: E402

from kavach.gateway import Gateway  # noqa: E402


class KavachAddon:
    def __init__(self) -> None:
        self.gw = Gateway.from_env()
        self.gw.trace.emit("gateway_started", detail=f"policy {self.gw.policy.get('pack')}")

    def request(self, flow: http.HTTPFlow) -> None:
        req = flow.request
        body = req.get_text(strict=False) or ""
        orig = (req.method, req.pretty_host, req.url, dict(req.headers), body)
        d = self.gw.on_request(*orig)
        flow.metadata["kavach"] = (orig, d, time.time())
        if not d.allow:
            self.gw.record_wire(*orig, d, status=403, ms=0.0,
                                agent_reply=json.dumps({"blocked_by": "kavach", "reason": d.reason}))
            flow.response = http.Response.make(
                403,
                json.dumps({"blocked_by": "kavach", "reason": d.reason}),
                {"content-type": "application/json"},
            )
            flow.metadata["kavach_blocked"] = True
            return
        if d.url != req.url:
            req.url = d.url
        if d.body != body:
            req.set_text(d.body)
        for k, v in d.headers.items():
            if req.headers.get(k) != v:
                req.headers[k] = v

    def response(self, flow: http.HTTPFlow) -> None:
        if flow.metadata.get("kavach_blocked") or flow.response is None:
            return
        text = flow.response.get_text(strict=False)
        if text is None:
            self._wire(flow, flow.response.status_code, None, "<binary>")
            return
        new = self.gw.on_response(flow.request.pretty_host, text)
        if new != text:
            flow.response.set_text(new)
        self._wire(flow, flow.response.status_code, text, new)

    def error(self, flow: http.HTTPFlow) -> None:
        if flow.metadata.get("kavach") and not flow.metadata.get("kavach_blocked"):
            self._wire(flow, 0, None, str(flow.error))

    def _wire(self, flow: http.HTTPFlow, status: int, upstream: str | None, agent: str) -> None:
        orig, d, t0 = flow.metadata["kavach"]
        self.gw.record_wire(*orig, d, status=status, upstream_reply=upstream, agent_reply=agent,
                            ms=(time.time() - t0) * 1000)


addons = [KavachAddon()]
