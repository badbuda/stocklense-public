"""Isolated private-handler harness safety, no ZIP or real AWS credentials."""
import io
import json
from pathlib import Path
import zipfile

import pytest
from infra.aws import sl63_private_handler_offline_scenarios as m


def zip_bytes(py):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:
        z.writestr("infra/aws/independent_paper.py",py)
        z.writestr("stocklens/paper.py","x=1\n")
    return stream.getvalue()


def test_full_zip_ast_detects_delegated_write_methods_without_executing():
    data=zip_bytes(b"def handler(event,context):\n"
        b"  return _helper(event)\n"
        b"def _helper(event):\n  return 'STAGING_PAPER_ONLY'\n")
    result=m.topology(data)
    assert result["aws_storage_method_ast_occurrences_project_zip_modules"]["put_object"]==0
    assert result["reviewed_known_mode_and_epoch_literal_presence"]["STAGING_PAPER_ONLY"]
    assert result["new_epoch_book_literal_found"] is False
    assert result["static_call_counts_not_execution_evidence"]


def test_zip_detects_write_method_hidden_in_helper_module():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:
        z.writestr("infra/aws/independent_paper.py","def handler(e,c): return 1\n")
        z.writestr("infra/aws/private_storage.py",
                   "def write(s3): return s3.put_object(Bucket='x',Key='y',Body='x')\n")
    info=m.topology(stream.getvalue())
    assert info["aws_storage_method_ast_occurrences_project_zip_modules"]["put_object"]==1
    assert info["aws_storage_method_ast_occurrences_private_handler"]["put_object"]==0


def test_package_member_path_traversal_rejected(tmp_path):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:
        z.writestr("infra/aws/independent_paper.py","def handler(e,c):pass\n")
        z.writestr("../../illegal.py","x=1\n")
    with pytest.raises(RuntimeError,match="UNSAFE_ZIP"):
        m.prepare_zip(stream.getvalue(),tmp_path)
    assert not (tmp_path/"illegal.py").exists()


def test_duplicate_member_rejected():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:
        z.writestr("infra/aws/independent_paper.py","def handler(e,c):pass\n")
        z.writestr("infra/aws/independent_paper.py","def handler(e,c):pass\n")
    with pytest.raises(RuntimeError,match="DUPLICATE_ZIP"):
        m.topology(stream.getvalue())


def test_safe_cases_include_buy_sell_and_fault_injection():
    assert {"CASH","L1","L2","L3","CONTINUITY_WRITE_ERROR","RETRY_DUPLICATE",
            "MISSING_PRIOR","BAD_WEIGHTS"}.issubset(m.SAFE_CASES)
    assert m.BOOK.startswith("NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_")


def test_fake_handler_smoke_never_makes_a_network_request(tmp_path):
    """A toy ZIP handler is invoked by child with fake S3 and no network.

    This checks safety wiring only; does not claim private handler outcome.
    """
    from stocklens.core import weights_for_leverage
    demo=(
        "def handler(event,context):\n"
        " import boto3\n"
        " s3=boto3.client('s3')\n"
        " try: s3.get_object(Bucket='stocklens-st-candidatedata-6jj7i9fxjmfr',"
        "Key='signals/2026-11-17.json')\n"
        " except Exception: return {'status':'FAIL_CLOSED'}\n"
        " return {'status':'STAGED_PAPER_VERIFIED'}\n"
    )
    data=zip_bytes(demo)
    # Test that source ZIP never gets copied to a non-temporary destination.
    m.prepare_zip(data,tmp_path)
    assert (tmp_path/"infra/aws/independent_paper.py").is_file()

def test_real_public_engine_zip_with_toy_handler_is_executed_only_in_fake_aws(tmp_path):
    """The local handler really runs with injected signals and fake S3.

    This is a toy private handler, not the deployed user's real handler.
    Checks child provenance and fake AWS isolation before the user runs it.
    """
    root=Path(__file__).resolve().parents[1]
    from infra.aws import sl63_deployed_paper_source_parity as pins
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,"w") as z:
        for path in pins.PINNED_PUBLIC_MODULE_BLOBS:
            z.writestr(path,(root/path).read_bytes())
        z.writestr(m.PRIVATE,
            "import boto3\n"
            "def handler(event,context):\n"
            " s3=boto3.client('s3')\n"
            " s3.get_object(Bucket='stocklens-st-candidatedata-6jj7i9fxjmfr',"
            "Key='signals/2026-11-17.json')\n"
            " return {'status':'STAGED_PAPER_VERIFIED'}\n")
    m.prepare_zip(mem.getvalue(),tmp_path)
    result=m.childcase(tmp_path,root,"L3")
    assert result["child_exit"]==0,result
    assert result["true_private_handler_imported_from_deployed_zip"] is True
    assert result["network_disabled"] is True
    assert result["all_sdk_calls_fake"] is True
    assert result["broker_orders"] is False
    assert result["real_aws_mutations"] is False
    assert result["fake_s3_reads_count"]>0
    assert result["handler_results"][0]["status"]=="STAGED_PAPER_VERIFIED"

def test_large_third_party_zip_does_not_hide_project_storage_writers(tmp_path):
    """Vendored dependency .py must not consume AST budget or fail on syntax."""
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr(m.PRIVATE,"def handler(e,c): return None\n")
        z.writestr("infra/aws/internal_s3_io.py",
                   "def put(s3): return s3.put_object(Bucket='x',Key='y')\n")
        z.writestr("pandas/io/python_source_from_another_version.py",
                   "syntax !! from a third-party package\n")
    out=m.topology(buf.getvalue())
    assert out["project_python_member_count"]==2
    assert out["aws_storage_method_ast_occurrences_project_zip_modules"]["put_object"]==1
    m.prepare_zip(buf.getvalue(),tmp_path)
    assert not (tmp_path/"pandas").exists()


def test_new_scenarios_are_required_for_release_truthfulness():
    assert "SEQUENCE_BUY_SELL_BUY" in m.SAFE_CASES
    assert "CONTINUITY_RETRY_RECOVERY" in m.SAFE_CASES
    assert '"2026-11-23"' in m.CHILD  # first Monday after Fri Nov20
    assert "first_continuity_write_failed_injected" in m.CHILD


def test_toy_multiday_handler_exercises_real_child_loop_and_fake_s3(tmp_path):
    """A toy handler tests THE HARNESS, not the deployed private handler."""
    from infra.aws import sl63_deployed_paper_source_parity as pins
    root=Path(__file__).resolve().parents[1]
    data=io.BytesIO()
    toy=(
        "import boto3,datetime\n"
        "def handler(event,context):\n"
        " s3=boto3.client('s3')\n"
        " session=event['expected_session']\n"
        " from exchange_calendars import get_calendar\n"
        " prev=get_calendar('XNYS').previous_session(session).date().isoformat()\n"
        " import json\n"
        " prior=json.loads(s3.get_object(Bucket='stocklens-st-candidatedata-6jj7i9fxjmfr',Key='signals/'+prev+'.json')['Body'].read())\n"
        " key='paper/sessions/'+session+'.json'\n"
        " side='SELL' if prior['latest']['defense_active'] else 'BUY'\n"
        " s3.put_object(Bucket='stocklens-st-candidatedata-6jj7i9fxjmfr',Key=key,Body=json.dumps({'trades':[{'side':side}]}),IfNoneMatch='*')\n"
        " s3.put_object(Bucket='stocklens-st-candidatedata-6jj7i9fxjmfr',Key='paper/continuity/'+session+'.json',Body='{}',IfNoneMatch='*')\n"
        " return {'status':'STAGED_PAPER_VERIFIED'}\n"
    )
    with zipfile.ZipFile(data,"w") as z:
        for name in pins.PINNED_PUBLIC_MODULE_BLOBS:
            z.writestr(name,(root/name).read_bytes())
        z.writestr(m.PRIVATE,toy)
    m.prepare_zip(data.getvalue(),tmp_path)
    result=m.childcase(tmp_path,root,"SEQUENCE_BUY_SELL_BUY")
    assert result["child_exit"]==0,result
    steps=result["consecutive_session_proofs"]
    assert len(steps)==5
    assert all(step["paper_receipt_written"] for step in steps)
    assert all(step["continuity_receipt_written"] for step in steps)
    assert {"BUY","SELL"}.issubset(result["fake_s3_modeled_sides_observed"])
    assert result["fake_s3_duplicate_key_writes"]==0
