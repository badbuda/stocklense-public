"""Static and fixture regression for read-only StockLens cross-stack AWS audit."""
from pathlib import Path
import subprocess
import pytest
from infra.aws import stocklens_live_evidence_audit as audit

def test_audit_script_compiles():
    subprocess.run(["python", "-m", "py_compile",
                    "infra/aws/stocklens_live_evidence_audit.py"], check=True)

def test_reject_mutating_aws_operation():
    with pytest.raises(RuntimeError, match="FORBIDDEN_AWS_ACTION"):
        audit.cli("events", "enable-rule", "--name", "stocklens-st-signal")

def test_missing_s3_is_distinct_from_permission_denied(monkeypatch):
    def fake(kind, op, *args):
        raise RuntimeError("An error occurred (404) when calling the HeadObject operation: Not Found")
    monkeypatch.setattr(audit, "cli", fake)
    assert audit.head("a", "signals/2026-10-28.json") == {"status": "MISSING"}
    def denied(kind, op, *args):
        raise RuntimeError("An error occurred (403) when calling the HeadObject operation: Forbidden")
    monkeypatch.setattr(audit, "cli", denied)
    assert audit.head("a", "signals/2026-10-28.json")["status"] == "READ_ERROR"

def test_all_four_env_names_distinct():
    assert len(set(audit.NEW + [audit.OLD])) == 4
    assert audit.ACCOUNT == "634740393398"
    assert audit.REGION == "eu-central-1"

def test_no_orders_backfill_or_mutating_shell_calls():
    text=Path("infra/aws/stocklens_live_evidence_audit.py").read_text()
    assert '"aws_mutations": False' in text
    assert '"lambda_invocations": False' in text
    assert '"history_backfilled": False' in text
    assert '("dynamodb", "get-item")' in text
    assert '("logs", "filter-log-events")' in text
    for forbidden in ('"put-object"', '"update-stack"', '"enable-rule"',
                      '"invoke"', '"put-item"', '"send-order"'):
        assert forbidden not in text

def test_absent_dynamodb_item_is_confirmed_missing_not_json_failure():
    class Client:
        def get_item(self, **kwargs):
            assert kwargs["ConsistentRead"] is True
            assert kwargs["Key"]["session_date"]["S"] in ("2026-10-28", "2026-10-28#PAPER")
            return {"ResponseMetadata":{"HTTPStatusCode":200}}
    data=audit.ddb("old-audit-table","2026-10-28",client=Client())
    assert data["2026-10-28"]=={"status":"MISSING","read_confirmed":True}
    assert data["2026-10-28#PAPER"]=={"status":"MISSING","read_confirmed":True}


def test_dynamodb_both_rows_present_with_hash_metadata_only():
    class Client:
        def get_item(self, **kwargs):
            key=kwargs["Key"]["session_date"]["S"]
            if key.endswith("#PAPER"):
                item={"session_date":{"S":key},"paper_sha256":{"S":"a"*64},
                      "paper_evidence_json":{"S":"private"}}
            else:
                item={"session_date":{"S":key},"signal_sha256":{"S":"b"*64},
                      "signal_json":{"S":"private"}}
            return {"ResponseMetadata":{"HTTPStatusCode":200},"Item":item}
    data=audit.ddb("old-audit-table","2026-10-28",client=Client())
    assert data["2026-10-28"]["status"]=="PRESENT"
    assert data["2026-10-28"]["signal_sha256"]=="b"*64
    assert data["2026-10-28#PAPER"]["paper_sha256"]=="a"*64
    assert "private" not in str(data)


def test_dynamodb_denied_not_misclassified_as_missing():
    class Denied(Exception):
        response={"Error":{"Code":"AccessDeniedException"}}
    class Client:
        def get_item(self, **kwargs):
            raise Denied("secret")
    data=audit.ddb("old-audit-table","2026-10-28",client=Client())
    assert all(x["status"]=="READ_ERROR" for x in data.values())
    assert all(x["error_code"]=="AccessDeniedException" for x in data.values())
    assert "secret" not in str(data)


def test_cloudwatch_log_pages_include_non_runtime_errors(monkeypatch):
    events=[
        {"eventId":"a","timestamp":1793190000000,"message":"START RequestId abc"},
        {"eventId":"b","timestamp":1793190005000,"message":"PAPER_PREFLIGHT_FAILED:missing prior signal"},
        {"eventId":"c","timestamp":1793190007000,"message":"END RequestId abc"},
    ]
    calls=[]
    def fake(service,operation,*args):
        assert (service,operation)==("logs","filter-log-events")
        calls.append(args)
        if len(calls)==1:
            return {"events":events[:2],"nextToken":"token-2"}
        return {"events":[events[1],events[2]],"nextToken":"token-2"}
    monkeypatch.setattr(audit,"cli",fake)
    x=audit.logs("stocklens-independent-staging-paper-candidate","2026-10-28")
    assert x["events_returned"]==3
    assert x["pages_read"]==2
    assert x["has_more_pages"] is False
    assert x["application_events_count"]==1
    assert x["potential_error_events_count"]==1
    assert "PAPER_PREFLIGHT_FAILED" in x["last_events"][0]["message"]
    assert x["runtime_event_tail"][0]["message"].startswith("START ")


def test_cloudwatch_log_pagination_cap_is_disclosed(monkeypatch):
    counter=[0]
    def fake(service,operation,*args):
        counter[0]+=1
        return {"events":[],"nextToken":"token-"+str(counter[0])}
    monkeypatch.setattr(audit,"cli",fake)
    x=audit.logs("st","2026-10-28")
    assert counter[0]==8
    assert x["truncated"] is True
    assert x["has_more_pages"] is True
