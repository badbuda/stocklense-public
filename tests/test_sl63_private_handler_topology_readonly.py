"""Static-only handler topology analysis, no execution of private code."""
import hashlib
import io
import json
import zipfile
import pytest
from infra.aws import sl63_private_handler_topology_readonly as m


EXAMPLE=b'''
import boto3
from stocklens.paper import rebalance_if_required

def preflight_handler(event, context):
    if event.get("mode")=="STAGING_PAPER_BOOTSTRAP_PREFLIGHT":
        return {"ok": True}

def handler(event, context):
    mode=event.get("mode")
    if mode == "STAGING_PAPER_ONLY":
        client=boto3.client("s3")
        client.put_object(Bucket="PRIVATE_DO_NOT_EXPOSE", Key="private-path")
        return {"status": "STAGED_PAPER_VERIFIED"}
    if mode == "STAGING_PAPER_SCHEDULE_READINESS":
        return {"status": "OK"}
    return {"status": "FAIL_CLOSED"}
'''


def test_inventory_preserves_private_literals_and_does_not_execute_code():
    data=m.analyze_private_source(EXAMPLE)
    assert data["handler_entrypoints"] == {"handler":True,"preflight_handler":True}
    assert data["documented_mode_literal_presence"]["STAGING_PAPER_ONLY"]
    assert data["documented_mode_literal_presence"]["STAGING_PAPER_BOOTSTRAP_PREFLIGHT"]
    assert data["documented_mode_literal_presence"]["STAGING_PAPER_SCHEDULE_READINESS"]
    assert data["sdk_method_name_occurrences_in_ast"]["put_object"] == 1
    assert data["potential_write_operation_names_present"] == ["put_object"]
    assert data["private_handler_sha256"]==hashlib.sha256(EXAMPLE).hexdigest()
    assert not data["private_handler_imported_or_executed"]
    assert not data["actual_handler_end_to_end_tested"]
    assert not data["source_disclosed"]
    blob=json.dumps(data)
    assert "PRIVATE_DO_NOT_EXPOSE" not in blob
    assert "private-path" not in blob
    assert "rebalance_if_required" not in blob


def test_missing_handler_fails_closed():
    with pytest.raises(RuntimeError,match="PRIVATE_HANDLER_ENTRYPOINT"):
        m.analyze_private_source(b"def other(event, ctx): return None")


def test_no_private_zip_path_rejected():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("stocklens/paper.py","public module")
    with pytest.raises(RuntimeError,match="PRIVATE_PAPER_HANDLER_MISSING"):
        m.source_from_verified_zip(buf.getvalue())


def test_duplicate_private_zip_entry_rejected():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr(m.SOURCE,EXAMPLE)
        z.writestr(m.SOURCE,EXAMPLE)
    with pytest.raises(RuntimeError,match="DUPLICATE_LAMBDA_ZIP"):
        m.source_from_verified_zip(buf.getvalue())


def test_zip_private_source_is_byte_exact_without_import():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr(m.SOURCE,EXAMPLE)
    assert m.source_from_verified_zip(buf.getvalue())==EXAMPLE


def test_ast_bad_source_fails_without_execution():
    with pytest.raises(SyntaxError):
        m.analyze_private_source(b"this is a broken syntax(")
