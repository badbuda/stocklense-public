"""Private, no-write tax report must reject missing FX provenance and position drift."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from research.private_tax_dashboard_export import build, _fx_hash


def receipt():
    row={"session_date":"2026-11-02","equity":2100.0,"cash":900.0,
        "qqq_shares":0,"tqqq_shares":10,"qqq_close":100.0,"tqqq_close":120.0,
        "fee_bps":2.0,"slippage_bps":10.0,"trade_count_session":0}
    trade={"execution_session":"2026-10-30","signal_date":"2026-10-29",
        "symbol":"TQQQ","side":"BUY","qty":10,"time_et":"09:32",
        "modeled_fill_price":100.0,"fee":0.0}
    data={"session":"2026-11-02","broker_fills_observed":False,
        "broker_orders_authorized":False,"row":row,
        "history":{"ledger":[{"session_date":"2026-10-30","trade_count_session":1},row],
                   "trades":[trade]}}
    raw=json.dumps(data,sort_keys=True).encode()
    return raw,hashlib.sha256(raw).hexdigest()


def inputs():
    fx={"2026-10-30":3.5,"2026-11-02":3.5}
    attest={"manually_verified":True,"fx_data_sha256":_fx_hash(fx),
            "independent_source":"INDEPENDENT_TEST_FIXTURE_ONLY",
            "verified_by":"test_fixture"}
    return fx,attest


def test_private_report_reconciles_cash_lots_and_hypothetical_terminal_tax():
    raw,sha=receipt()
    fx,att=inputs()
    report=build(raw,sha,fx,att)
    assert report["status"]=="RESEARCH_COMPLETE"
    assert report["source"]=="PRIVATE_SHA_VERIFIED_ST_PAPER"
    assert report["estimated_tax_assessed_ils"]==0
    assert report["estimated_additional_exit_tax_ils"]>0
    assert 1800<report["estimated_after_tax_liquidation_usd"]<2100
    assert report["actual_broker_tax_withheld_ils"] is None
    assert report["capital_trading_authorized"] is False
    assert report["fx_attestation_scope"]=="HUMAN_ATTESTED_SOURCE_NOT_AUTOMATICALLY_VERIFIED"


def test_missing_fx_attestation_rejected_even_with_balanced_paper():
    raw,sha=receipt()
    fx,att=inputs()
    with pytest.raises(ValueError,match="FX_ATTESTATION"):
        build(raw,sha,fx,{})
    with pytest.raises(ValueError,match="FX_ATTESTATION"):
        build(raw,sha,fx,{**att,"fx_data_sha256":"0"*64})


def test_receipt_hash_and_paper_nav_are_not_inferred():
    raw,sha=receipt()
    fx,att=inputs()
    with pytest.raises(ValueError,match="SHA"):
        build(raw,"0"*64,fx,att)
    data=json.loads(raw)
    data["row"]["equity"]+=50
    edited=json.dumps(data,sort_keys=True).encode()
    with pytest.raises(ValueError,match="PAPER_NAV"):
        build(edited,hashlib.sha256(edited).hexdigest(),fx,att)


def test_aws_route_is_jwt_getonly_and_no_account_mutations():
    y=Path("infra/aws/tax-research-private-readonly-route.yaml").read_text()
    assert "AuthorizationType: JWT" in y
    assert "AuthorizerId: !Ref PortalAuthorizerId" in y
    assert "RouteKey: GET /v1/tax" in y
    assert "Action: s3:GetObject" in y
    assert "tax-research/private/*" in y
    assert "s3:PutObject" not in y
    assert "dynamodb:PutItem" not in y
    assert "lambda:InvokeFunction" in y
