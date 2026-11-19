"""Unit-level, no AWS credentials needed: source ZIP parity must fail closed."""
import base64
import hashlib
import io
from pathlib import Path
import zipfile

import pytest
from infra.aws import sl63_deployed_paper_source_parity as m


def zipped(payload):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in payload.items():
            z.writestr(name,data)
    return buf.getvalue()


def public_payload():
    root=Path(__file__).resolve().parents[1]
    return {name:(root/name).read_bytes()
            for name in m.PINNED_PUBLIC_MODULE_BLOBS}


def test_same_source_zip_passes_byte_parity():
    root=Path(__file__).resolve().parents[1]
    m.assert_local_pins(root)
    data,handler=m.inspect_zip(zipped(public_payload()),root)
    assert all(x["matches_tested_code"] for x in data.values())
    assert handler["handler_executed"] is False


def test_modified_economic_model_fails_source_parity():
    payload=public_payload()
    payload["stocklens/paper.py"]+=b"\n# changed\n"
    data,_=m.inspect_zip(zipped(payload),Path("."))
    assert not data["stocklens/paper.py"]["matches_tested_code"]


def test_missing_deployed_module_is_not_silently_replaced_from_git():
    payload=public_payload()
    del payload["stocklens/paper.py"]
    data,_=m.inspect_zip(zipped(payload),Path("."))
    assert not data["stocklens/paper.py"]["bundled"]
    with pytest.raises(RuntimeError,match="DEPLOYED_MODULE_UNAVAILABLE"):
        m.execute_deployed_economic_module_scenarios(zipped(payload),Path("."))


def test_bogus_lambda_code_sha_and_handler_are_rejected():
    cfg={
        "FunctionName":m.NAME, "State":"Active",
        "LastUpdateStatus":"Successful","Handler":m.HANDLER,
        "CodeSha256":m.PINNED_LAMBDA_SHA_B64,
        "Environment":{"Variables":{"STOCKLENS_DATA_BUCKET":m.ST_BUCKET}}
    }
    m.validate_config(cfg)
    for key,value in (("Handler","unsafe.handler"),
                      ("CodeSha256","DIFFERENT_SHA"),
                      ("State","Failed")):
        faulty=dict(cfg,key=value)
        with pytest.raises(RuntimeError):
            m.validate_config(faulty)


def test_reject_zip_traversal_and_duplicate_paths():
    payload=public_payload()
    payload["../steal.py"]=b"import os"
    with pytest.raises(RuntimeError,match="UNSAFE_ZIP_FILE_NAMES"):
        m.inspect_zip(zipped(payload),Path("."))
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("stocklens/paper.py","one")
        z.writestr("stocklens/paper.py","two")
    with pytest.raises(RuntimeError,match="DUPLICATE_ZIP_ENTRIES"):
        m.inspect_zip(buf.getvalue(),Path("."))
