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
        stream.writestr("infra/aws/independent_paper.py",
            b"def run_scheduled_paper(now):\n"
            b"    from infra.aws.independent_orchestrator import current_completed_session\n"
            b"\n    day = current_completed_session(now)\n"
            b"    return day\n")
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
        assert b"completed_session_for_scheduled_attempt(now)" in zipped.read("infra/aws/independent_paper.py")
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


def test_unexpected_paper_handler_is_blocked_without_unsafe_overwrite(monkeypatch):
    old = b"# old"
    new = b"# new"
    monkeypatch.setattr(release, "EXPECTED", {
        "infra/aws/independent_pipeline.py": (
            release.blob(old), release.blob(new)),
    })
    original = io.BytesIO()
    with zipfile.ZipFile(original, "w") as z:
        z.writestr("infra/aws/independent_pipeline.py", old)
        z.writestr("infra/aws/independent_paper.py", b"def changed_private_handler(): pass")
        for i in range(120):
            z.writestr(f"deps/something_{i}.py", b"x=1\n")
    with pytest.raises(RuntimeError, match="PRIVATE_PAPER_SCHEDULE_RESOLVER_CHANGED"):
        release.prepare_zip(original.getvalue(), fetch=lambda _: new)


def test_release_pinned_and_last_retry_before_open():
    assert release.REF == "71843e50d7b283baba5b2d8962b599622e0acd7a"
    assert release.UPDATED["CandidateSignalOnlyRuleName"] == "cron(30 5,8,11,12 ? * TUE-SAT *)"
    assert release.UPDATED["CandidatePaperOnlyRuleName"] == "cron(0 13 ? * TUE-SAT *)"
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


def synthetic_private_watchdog(extra=""):
    before, _ = release.WATCHDOG_CHANGES[0]
    due, _ = release.WATCHDOG_CHANGES[1]
    invoke, _ = release.WATCHDOG_CHANGES[2]
    return (
        "from infra.aws.independent_signal_monitor import due_signal_sessions\n"
        "import os\n"
        + extra + "\n"
        "def inspect(*, now, signal_activation_at, \n"
        + before + "\n"
        + due + "\n"
        "                    return []\n\n"
        "def handler(event, context):\n"
        "    def read_signal_activation():\n"
        "        return None\n"
        "    cw.put_metric_data(Namespace='StockLens/IsolatedST', MetricData=[])\n"
        "    return inspect(\n"
        + invoke + "\n"
    ).encode("utf-8")


def test_private_watchdog_can_be_modified_only_at_three_expected_call_sites():
    old = synthetic_private_watchdog("ISOLATED_PRIVATE_MONITORING = 'retained'")
    result = release.patch_private_watchdog(old)
    assert b"ISOLATED_PRIVATE_MONITORING = 'retained'" in result
    assert b"v2_start_session=signal_v2_start_session" in result
    assert b"SIGNAL_V2_START_SESSION" in result
    assert b"signal_v2_start_session: str | None = None" in result
    assert result != old
    reconstructed = result.decode()
    for before, after in reversed(release.WATCHDOG_CHANGES):
        assert reconstructed.count(after) == 1
        reconstructed = reconstructed.replace(after, before, 1)
    assert reconstructed.encode() == old


def test_unknown_private_watchdog_semantics_are_blocked(monkeypatch):
    source = synthetic_private_watchdog().decode().replace(
        "due_signal_sessions(now, signal_activation_at)",
        "due_signal_sessions(now, signal_activation_at, some_new_behavior=True)",
    ).encode()
    with pytest.raises(RuntimeError, match="PRIVATE_WATCHDOG_V2_ANCHOR_CHANGED"):
        release.patch_private_watchdog(source)


def test_repeated_patch_is_blocked_without_new_approval():
    first = release.patch_private_watchdog(synthetic_private_watchdog())
    with pytest.raises(RuntimeError, match="V2_ANCHOR_CHANGED|V2_ALREADY_PRESENT"):
        release.patch_private_watchdog(first)


def test_deployed_watchdog_private_isolation_drift_preserved_in_final_zip(monkeypatch):
    """Regression for the exact 2026-11-10 user-reported source-hash blocker."""
    previous_pipeline = b"# original scheduled signal source\n"
    new_pipeline = b"# vetted scheduled signal source\n"
    new_policy = b"# pinned signal retry module\n"
    reference_watchdog = synthetic_private_watchdog()
    private_watchdog = synthetic_private_watchdog(
        "ISOLATED_ST_METRICS_PRESERVED = 'private-release'"
    )
    candidate_watchdog = release.patch_private_watchdog(reference_watchdog)
    monkeypatch.setattr(release, "EXPECTED", {
        "infra/aws/independent_pipeline.py": (
            release.blob(previous_pipeline), release.blob(new_pipeline)),
        "infra/aws/independent_session_watchdog.py": (
            release.blob(reference_watchdog), release.blob(candidate_watchdog)),
        "stocklens/st_signal_retry_policy.py": (
            None, release.blob(new_policy)),
    })
    baseline = io.BytesIO(fake_zip(previous_pipeline))
    with zipfile.ZipFile(baseline, "a") as archive:
        archive.writestr("infra/aws/independent_session_watchdog.py", private_watchdog)
    source_map = {
        "infra/aws/independent_pipeline.py": new_pipeline,
        "infra/aws/independent_session_watchdog.py": candidate_watchdog,
        "stocklens/st_signal_retry_policy.py": new_policy,
    }
    payload = release.prepare_zip(baseline.getvalue(), fetch=source_map.__getitem__)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        deployed = archive.read("infra/aws/independent_session_watchdog.py")
        assert b"ISOLATED_ST_METRICS_PRESERVED = 'private-release'" in deployed
        assert b"v2_start_session=signal_v2_start_session" in deployed
        assert archive.read("infra/aws/independent_pipeline.py") == new_pipeline
        assert archive.read("stocklens/st_signal_retry_policy.py") == new_policy
        assert len(archive.namelist()) == len(set(archive.namelist()))
