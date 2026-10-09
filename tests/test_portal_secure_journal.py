"""Offline security contract of Cognito-protected, GetItem-only journal API."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SOURCE=Path("infra/aws/portal-journal-handler.py")
TEMPLATE=Path("infra/aws/portal-readonly-api.yaml")
PORTAL=Path("docs/portal-cloud.js")
INSIGHTS=Path("docs/portal-insights.js")


def load_handler():
    spec=importlib.util.spec_from_file_location("readonly_portal_handler",SOURCE)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archived_pair(day="2026-10-08"):
    signal={"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "latest":{"asof_date":day,"level":3,"target_leverage":3.0}}
    paper={"row":{"session_date":day,"execution_source":"YFINANCE_1M_RAW",
                  "trade_count_session":1,"equity":97427.96},
           "trs":[{"execution_session":day,"symbol":"TQQQ","side":"BUY","qty":1197}]}
    s=json.dumps(signal,separators=(",",":"))
    p=json.dumps(paper,separators=(",",":"))
    return {
      day:{"broker_orders_authorized":False,"signal_json":s,
           "signal_sha256":hashlib.sha256(s.encode()).hexdigest(),
           "recorded_at_utc":"2026-10-09T09:10:34Z"},
      day+"#PAPER":{"broker_orders_authorized":False,
            "broker_fills_observed":False,"paper_evidence_json":p,
            "paper_sha256":hashlib.sha256(p.encode()).hexdigest(),
            "recorded_at_utc":"2026-10-09T09:20:34Z"}
    }


def test_valid_read_returns_verified_broker_disabled_evidence():
    module=load_handler()
    data=archived_pair()
    row=module.read_session("2026-10-08",data.get)
    assert row["status"]=="PASS"
    assert row["signal"]["level"]==3
    assert row["paper"]["row"]["equity"]==97427.96
    assert row["paper"]["trades"][0]["symbol"]=="TQQQ"


def test_missing_session_and_missing_either_side_are_explicit():
    module=load_handler()
    data=archived_pair()
    assert module.read_session("2026-10-09",data.get)["status"]=="MISSING_BOTH"
    data.pop("2026-10-08#PAPER")
    assert module.read_session("2026-10-08",data.get)["status"]=="MISSING_PAPER"


@pytest.mark.parametrize("change",[
    lambda d: d["2026-10-08"].update(signal_sha256="0"*64),
    lambda d: d["2026-10-08#PAPER"].update(paper_sha256="0"*64),
    lambda d: d["2026-10-08"].update(broker_orders_authorized=True),
    lambda d: d["2026-10-08#PAPER"].update(broker_fills_observed=True),
])
def test_corruption_and_broker_claims_fail_closed(change):
    module=load_handler()
    data=archived_pair()
    change(data)
    result=module.read_session("2026-10-08",data.get)
    assert result["status"]=="INVALID_EVIDENCE"
    assert result["signal"] is None and result["paper"] is None


def test_dates_are_bounded_and_reject_malformed():
    module=load_handler()
    assert module.require_dates("2026-10-08,2026-10-09")==["2026-10-08","2026-10-09"]
    for bad in ("","2026-13-99","2026-10-08,2026-10-08",
                ",".join(["2026-10-08"]*31), "../../etc/passwd", "2050-01-01"):
        with pytest.raises(ValueError):
            module.require_dates(bad)


def test_handler_rejects_unauthenticated_http_method_before_dynamodb():
    module=load_handler()
    result=module.handler({"requestContext":{"http":{"method":"POST"}}},None)
    assert result["statusCode"]==405
    result=module.handler({"requestContext":{"http":{"method":"GET"}},
                           "queryStringParameters":{}},None)
    assert result["statusCode"]==400


def test_template_contains_exact_runtime_source_and_restricted_iam():
    t=TEMPLATE.read_text(encoding="utf-8")
    raw=SOURCE.read_text(encoding="utf-8").strip().splitlines()
    start=t.index("        ZipFile: |\n")+len("        ZipFile: |\n")
    end=t.index("\n  JournalApi:",start)
    body=t[start:end].splitlines()
    assert "\n".join(x[10:] for x in body).strip()=="\n".join(raw)
    assert "Action: [dynamodb:GetItem]" in t
    for action in ("dynamodb:Scan","dynamodb:PutItem","dynamodb:UpdateItem",
                   "dynamodb:DeleteItem","dynamodb:*","execute-api:Invoke"):
        assert action not in t
    assert "AuthorizationType: JWT" in t
    assert "AuthorizerType: JWT" in t
    assert "AllowAdminCreateUserOnly: true" in t
    assert "AllowedOAuthFlows: [code]" in t
    assert "GenerateSecret: false" in t
    assert "AllowOrigins: [!Ref AmplifyOrigin]" in t


def test_browser_uses_pkce_and_never_persists_tokens():
    s=PORTAL.read_text()
    assert "code_challenge_method:'S256'" in s
    assert "authorization_code" in s
    assert "crypto.subtle.digest('SHA-256'" in s
    assert "Authorization':'Bearer '" in s
    assert "localStorage" not in s
    assert "setItem('access_token'" not in s
    assert "enabled!==true" in s
    assert "STOCKLENS_AUTHENTICATED_READ_ONLY_AWS_JOURNAL" in s
    assert "broker_orders_authorized!==false" in s


def test_insights_support_detail_source_gap_and_scenario_comparison():
    s=INSIGHTS.read_text()
    for token in ("inspectTrade","forwardGapReport","missingBetween",
                  "UNVERIFIED_EXCHANGE_CALENDAR","compareScenarioData",
                  "updateScenarioComparison"):
        assert token in s
    assert "broker" in s.lower()
