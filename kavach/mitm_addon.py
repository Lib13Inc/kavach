"""mitmproxy add-on: the Kavach gateway on the wire.

    mitmdump --listen-port 8080 -s kavach/mitm_addon.py

Environment: KAVACH_POLICY, KAVACH_TRACE, plus the REAL API keys
(ANTHROPIC_API_KEY, OPENAI_API_KEY). The agent container never gets those.
"""
import json
import os
import sys

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
        d = self.gw.on_request(req.method, req.pretty_host, req.url, dict(req.headers), body)
        if not d.allow:
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
            return
        new = self.gw.on_response(flow.request.pretty_host, text)
        if new != text:
            flow.response.set_text(new)


addons = [KavachAddon()]
