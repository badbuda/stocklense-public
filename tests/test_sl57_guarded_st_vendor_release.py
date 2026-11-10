"""Offline SL-57 release harness — never touches AWS, S3 or broker."""
from __future__ import annotations
import io
import zipfile
from pathlib import Path

import pytest

from infra.aws import sl57_guarded_st_vendor_release as release


def fake_zip(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as stream:
        stream.writestr("infra/aws/independent_pipeline.py", payload)
        for i in range(120):
            stream.writestr(f"deps/submodule_{i}.py", b"# keep immutable dependency\n")
    return buffer.getvalue()


def test_pinned_source_and_no_hidden_existing_module(monkeypatch):
    prior = b"# known deployed code\n"
    newer = b"# exactly audited candidate code\n"
    module = b"# new policy module\n"
    monkeypatch.setattr(release, "EXPECTED", {
        "infra/aws/independent_pipeline.py": (
            release.blob(prior), release.blob(newer)),
        "stocklens/st_signal_retry_policy.py": (
            None, release.blob(module)),
    })
    mapping = {
        "infra/aws/independent_pipeline.py": newer,
        "stocklens/st_signal_retry_policy.py": module,
    }
    candidate = release.prepare_zip(fake_zip(prior), fetch=mapping.__getitem__)
    with zipfile.ZipFile(io.BytesIO(candidate)) as zipped:
        assert zipped.read("infra/aws/independent_pipeline.py") == newer
        assert zipped.read("stocklens/st_signal_retry_policy.py") == module
        assert zipped.read("deps/submodule_53.py") == b"# keep immutable dependency\n"
        assert len(zipped.namelist()) == len(set(zipped.namelist()))


def test_unknown_live_source_fails_closed_before_any_mutation(monkeypatch):
    prior = b"known source"
    monkeypatch.setattr(release, "EXPECTED", {
        "infra/aws/independent_pipeline.py": (
            release.blob(prior), release.blob(b"new")),
    })
    with pytest.raises(RuntimeError, match="PRIVATE_LAMBDA_SOURCE_CHANGED"):
        release.prepare_zip(fake_zip(b"changed private source"), fetch=lambda _: b"new")


def test_release_pinned_and_last_retry_before_open():
    assert release.REF == "189f63fb382d28479162018a085243b2ffca1487"
    assert release.UPDATED["CandidateSignalOnlyRuleName"] == "cron(30 5,8,11,12 ? * TUE-SAT *)"
    assert release.UPDATED["CandidatePaperOnlyRuleName"] == "cron(45 12 ? * TUE-SAT *)"
    assert release.OLD["CandidateSignalOnlyRuleName"] == "cron(30 2 ? * TUE-SAT *)"


def test_no_production_lambda_or_alarm_actions_in_release_script():
    source = Path("infra/aws/sl57_guarded_st_vendor_release.py").read_text()
    assert "update_function_code(" in source
    assert "update_function_configuration(" in source
    assert "put_rule(" in source
    assert "set_alarm_state(" not in source
    assert "execute_change_set(" not in source
    assert "update_stack(" not in source
    assert "delete_object(" not in source
    assert "send_order(" not in source
    assert "PROD_SCHEDULE_CHANGED" in source
    assert "APPLY_REQUIRES_EXPLICIT_APPROVAL_FLAGS" in source
    assert "PRIVATE_LAMBDA_SOURCE_CHANGED" in source
