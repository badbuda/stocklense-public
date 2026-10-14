"""Source integrity tests: second vendor, broker-read-only, private AWS staging portal."""
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal
import hashlib
import json
import subprocess
from pathlib import Path
import pytest

from infra.aws.second_vendor_parity import audit, parse_csv, PROVIDER
from infra.aws.staging_portal_read import verified_body, summarize
from broker_readonly_evidence import positions_csv, reconcile_readonly

def _history(rows=650):
    d=date(2024,1,1)
    days=[]
    while len(days)<rows:
        if d.weekday()<5:
            days.append(d.isoformat())
        d+=timedelta(days=1)
    return days

def _csv(days, prices):
    return ("Date,Close\n"+"".join(f"{d},{p:.9f}\n" for d,p in zip(days,prices))).encode()

def test_two_vendor_equal_policy_does_not_authorize_live_trade_or_claim_precision():
    ds=_history()
    values=[100+(i*.031)+.2*(i%9) for i in range(len(ds))]
    original=_csv(ds,values)
    r=audit(frozen_csv=original,independent_csv=original,
            expected_session=ds[-1],vendor=PROVIDER,adjustment="all",
            licensed_asof=ds[-1])
    assert r["status"]=="SECOND_VENDOR_POLICY_DIAGNOSTIC_MATCH"
    assert r["calendar_equal"] is True
    assert r["second_provider_data_received"] is True
    assert r["source_adjustment_reconciled"] is False
    assert r["second_provider_proven"] is False
    assert r["production_cutover_approved"] is False
    assert r["broker_actions"] is False
    assert r["policy_disagreement_count"]==0

def test_second_vendor_rejects_mismatched_adjustment_source_and_calendar():
    ds=_history()
    data=_csv(ds,[100+i*.1 for i in range(len(ds))])
    for kwargs in [{"vendor":"YAHOO_CHART","adjustment":"all"},
                   {"vendor":PROVIDER,"adjustment":"raw"}]:
        with pytest.raises(ValueError,match="INDEPENDENT_ADJUSTED_VENDOR"):
            audit(frozen_csv=data,independent_csv=data,expected_session=ds[-1],
                  licensed_asof=ds[-1],**kwargs)
    bad=_csv(ds[1:],[100+i*.1 for i in range(len(ds)-1)])
    r=audit(frozen_csv=data,independent_csv=bad,expected_session=ds[-1],
            licensed_asof=ds[-1],vendor=PROVIDER,adjustment="all")
    assert r["status"]=="SECOND_VENDOR_CALENDAR_MISMATCH"
    assert r["second_provider_proven"] is False

@pytest.mark.parametrize("data",[
    b"Symbol,Quantity\nTQQQ,1\nTQQQ,2\n",
    b"Symbol,Quantity\nTQQQ,-1\n",
    b"Symbol,Quantity\nTQQQ,NaN\n",
    b"Symbol,Quantity\nTQQQ,1e1000000\n",
    b"Account,Quantity\n001,5\n",
])
def test_broker_export_fail_closed(data):
    with pytest.raises(ValueError):
        positions_csv(data,name="EXCELLENCE")

def test_readonly_broker_match_never_changes_broker_or_live_gate():
    a=b"Symbol,Quantity\nQQQ,1.5\nTQQQ,20\n"
    now=datetime(2026,10,14,5,tzinfo=timezone.utc)
    r=reconcile_readonly(intended_csv=a,observed_csv=a,
         snapshot_at_utc=now-timedelta(hours=1),now=now)
    assert r["status"]=="MATCH_READ_ONLY_NOT_TRADE_AUTHORIZATION"
    assert r["live_gate_eligible"] is False
    assert r["broker_order_approval"] is False
    assert r["api_account_ownership_proven"] is False
    assert r["broker_actions"] is False
    differing=b"Symbol,Quantity\nQQQ,1.5\nTQQQ,18\n"
    mismatch=reconcile_readonly(intended_csv=a,observed_csv=differing,
         snapshot_at_utc=now,now=now)
    assert mismatch["differences"][0]["symbol"]=="TQQQ"
    assert mismatch["live_gate_eligible"] is False
    with pytest.raises(ValueError,match="STALE"):
        reconcile_readonly(intended_csv=a,observed_csv=a,
              snapshot_at_utc=now-timedelta(days=4),now=now)

def _evidence(obj):
    b=json.dumps(obj,sort_keys=True).encode()
    return verified_body(b,"v123","2026-10-14T01:30:00+00:00")

def test_portal_s3_summary_validates_signal_paper_and_continuity_and_never_claims_broker():
    day="2026-10-13"
    sig={"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
         "latest":{"asof_date":day,"level":3,"target_leverage":3.0},
         "execution_plan":{"broker_actions_enabled":False}}
    sr=_evidence(sig)
    paper={"session":day,"broker_orders_authorized":False,
           "broker_fills_observed":False,"production_replacement_authorized":False,
           "integrity":{"status":"PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"},
           "current_signal_sha256":sr[1]["sha256"],
           "row":{"equity":97427.96},"trades":[]}
    pr=_evidence(paper)
    continuity={"session":day,"status":"ON_TIME_QUALIFIED",
                "evidence":{"paper_sha256":pr[1]["sha256"]}}
    cr=_evidence(continuity)
    d={"signals/"+day+".json":sr,"paper/sessions/"+day+".json":pr,
       "paper/continuity/"+day+".json":cr}
    result=summarize(day,d.get)
    assert result["status"]=="SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND"
    assert result["paper"]["equity"]==97427.96
    assert result["paper"]["continuity_status"]=="ON_TIME_QUALIFIED"
    assert "account_id" not in json.dumps(result).lower()
    bad=dict(d)
    bad["signals/"+day+".json"]=_evidence({**sig,"execution_plan":{"broker_actions_enabled":True}})
    assert summarize(day,bad.get)["status"]=="INVALID_EVIDENCE"
    assert summarize(day,lambda _:None)["status"]=="NO_STAGING_RECEIPT"

def test_staging_portal_s3_checks_explicit_versions_and_max_bytes():
    with pytest.raises(ValueError,match="UNVERSIONED"):
        verified_body(b"{}","null","time")
    with pytest.raises(ValueError,match="TOO_LARGE"):
        verified_body(b"x"*2000001,"v1","time")

def test_portal_api_requires_existing_jwt_and_s3_get_only():
    import yaml
    class Loader(yaml.SafeLoader): pass
    Loader.add_multi_constructor("!",lambda ld,suffix,node:suffix+":"+str(node.value))
    doc=yaml.load(Path("infra/aws/staging-portal-readonly.yaml").read_text(),Loader=Loader)
    r=doc["Resources"]
    role=r["StagingPortalReadRole"]["Properties"]
    statements=role["Policies"][0]["PolicyDocument"]["Statement"]
    permissions=set()
    for x in statements:
        a=x["Action"]
        permissions.update(a if isinstance(a,list) else [a])
    assert permissions=={"s3:GetObject","s3:GetObjectVersion","s3:ListBucket"}
    assert r["StagingPortalRoute"]["Properties"]["AuthorizationType"]=="JWT"
    assert r["StagingPortalRoute"]["Properties"]["AuthorizerId"]=="Ref:PortalAuthorizerId"
    assert r["AllowStagingPortalApiInvoke"]["Properties"]["SourceArn"].endswith("/GET/v1/staging")
    assert "s3:PutObject" not in str(statements)
    code=r["StagingPortalReadLambda"]["Properties"]["Code"]["ZipFile"]
    assert "STOCKLENS_AUTHENTICATED_STAGING_S3_READ_ONLY" in code
    assert "verified_body" in code and "summarize" in code
    assert "StagingDataBucket" in doc["Parameters"]
    api=Path("infra/aws/portal-readonly-api.yaml").read_text()
    assert "PortalAuthorizerId:" in api and "PortalApiId:" in api

def test_portal_ui_staging_button_is_locked_behind_cognito_connection():
    h=Path("docs/portal.html").read_text()
    s=Path("docs/portal-cloud.js").read_text()
    assert 'id="cloud-staging-load"' in h
    assert 'id="cloud-staging-results"' in h
    assert "cfg.staging_enabled!==true" in s
    assert "refreshStagingEvidence" in s
    assert "/v1/staging?dates=" in s
    assert "full_chain_verified_by_portal!==false" in s
    subprocess.run(["node","--check","docs/portal-cloud.js"],check=True)
