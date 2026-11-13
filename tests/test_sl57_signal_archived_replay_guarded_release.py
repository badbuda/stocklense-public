"""Offline safety contracts for 2026-11-10 revised-Yahoo Signal retry patch."""
import io
import zipfile
import pytest
from infra.aws import sl57_signal_archived_replay_guarded_release as release


def old_package(pipeline: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(release.PATH, pipeline)
        z.writestr("stocklens/st_signal_retry_policy.py", b"# immutable retry policy\n")
        for i in range(120):
            z.writestr(f"private/code_{i}.py", b"# preserve all private files\n")
    return out.getvalue()


def test_signal_replay_patch_only_replaces_exact_source_and_retains_private_code(monkeypatch):
    before, after = b"# known old Signal\n", b"# offline verified replay candidate\n"
    original = old_package(before)
    monkeypatch.setattr(release, "CURRENT_ZIP_SHA256_B64", release.sha256_b64(original))
    monkeypatch.setattr(release, "OLD_PIPELINE_GIT_BLOB_SHA", release.blob_sha(before))
    monkeypatch.setattr(release, "NEW_PIPELINE_GIT_BLOB_SHA", release.blob_sha(after))
    modified = release.patch_zip(original, after)
    with zipfile.ZipFile(io.BytesIO(original)) as old, zipfile.ZipFile(io.BytesIO(modified)) as new:
        assert new.namelist() == old.namelist()
        assert new.read(release.PATH) == after
        for name in old.namelist():
            if name != release.PATH:
                assert new.read(name) == old.read(name)
    assert release.sha256_b64(modified) != release.sha256_b64(original)


def test_code_sha_mismatch_fails_before_mutation(monkeypatch):
    before, after = b"before", b"after"
    original = old_package(before)
    monkeypatch.setattr(release, "OLD_PIPELINE_GIT_BLOB_SHA", release.blob_sha(before))
    monkeypatch.setattr(release, "NEW_PIPELINE_GIT_BLOB_SHA", release.blob_sha(after))
    with pytest.raises(RuntimeError, match="DEPLOYED_LAMBDA_ZIP_CHANGED_STOP"):
        release.patch_zip(original, after)


def test_private_pipeline_delta_blocks_patch_even_if_zip_sha_has_changed(monkeypatch):
    before, after = b"before", b"after"
    original = old_package(before)
    monkeypatch.setattr(release, "CURRENT_ZIP_SHA256_B64", release.sha256_b64(original))
    monkeypatch.setattr(release, "OLD_PIPELINE_GIT_BLOB_SHA", release.blob_sha(b"other"))
    monkeypatch.setattr(release, "NEW_PIPELINE_GIT_BLOB_SHA", release.blob_sha(after))
    with pytest.raises(RuntimeError, match="DEPLOYED_PIPELINE_SOURCE_CHANGED_STOP"):
        release.patch_zip(original, after)


def test_signal_only_no_broker_no_s3_or_eventbridge_mutations():
    from pathlib import Path
    script = Path("infra/aws/sl57_signal_archived_replay_guarded_release.py").read_text()
    assert "update_function_code(" in script
    for forbidden in ("update_function_configuration(", "put_rule(", "delete_rule(",
                      "put_object(", "delete_object(", "set_alarm_state(", "update_stack(",
                      "execute_change_set(", "place_order("):
        assert forbidden not in script
    assert 'CURRENT_ZIP_SHA256_B64 = "YKpLN8Ks36blX4J9z+GnDKx9fCN87tA7wwc5Sc/25WQ="' in script
    assert "APPLY_REQUIRES_EXPLICIT_ST_APPROVAL" in script
    assert "ST_SIGNAL_VERIFIED_REPLAY_PATCH_DEPLOYED" in script
