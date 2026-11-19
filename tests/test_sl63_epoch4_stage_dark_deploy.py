"""Test CloudFormation dark deployment constraints with NO cloud credentials."""
from io import BytesIO
from pathlib import Path
import zipfile
import pytest
from infra.aws import sl63_epoch4_stage_dark_deploy as d
from infra.aws import sl63_deployed_paper_source_parity as pins


def test_cfn_has_only_dark_lambda_iam_and_logs():
    t=d.template("deployment/epoch4/dark/sha.zip",
       {"Runtime":"python3.13","Architectures":["x86_64"],
        "Layers":[],"MemorySize":512})
    types={r["Type"] for r in t["Resources"].values()}
    assert types=={"AWS::IAM::Role","AWS::Logs::LogGroup",
                   "AWS::Lambda::Function"}
    fn=t["Resources"]["DarkLambda"]["Properties"]
    assert fn["Environment"]["Variables"]["STOCKLENS_EPOCH4_WRITE_ENABLED"]=="false"
    assert fn["FunctionName"]==d.FUNCTION
    assert fn["Handler"]==d.HANDLER
    assert fn["Code"]["S3Bucket"]==d.BUCKET
    stm=t["Resources"]["DarkRole"]["Properties"]["Policies"][0]
    rules=stm["PolicyDocument"]["Statement"]
    writes=next(x for x in rules if "s3:PutObject" in x["Action"])
    assert len(writes["Resource"])==3
    assert all("/paper/epochs/"+d.store.EPOCH+"/" in r
               for r in writes["Resource"])
    assert all("/signals/" not in r and "prod" not in r.lower()
               for r in writes["Resource"])
    assert not any("EventBridge" in x or "Events::Rule" in x
                   for x in types)


def test_wrong_runtime_fails_closed():
    with pytest.raises(RuntimeError,match="UNEXPECTED_ST_RUNTIME"):
        d.template("artifact",{"Runtime":"nodejs20.x"})


def test_packaging_strips_private_legacy_handler_and_preserves_model():
    buf=BytesIO()
    root=Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(buf,"w") as z:
        for path in pins.PINNED_PUBLIC_MODULE_BLOBS:
            z.writestr(path,(root/path).read_bytes())
        for name in d.EXCLUDE:
            z.writestr(name,"def handler(event, ctx): pass")
    out=d.package(buf.getvalue(),root)
    with zipfile.ZipFile(BytesIO(out)) as z:
        assert "infra/aws/sl63_epoch4_lambda.py" in z.namelist()
        assert all(n not in z.namelist() for n in d.EXCLUDE)
        assert z.read("stocklens/paper.py")==(
            root/"stocklens/paper.py").read_bytes()


def test_tampered_old_economic_code_does_not_package():
    buf=BytesIO()
    root=Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(buf,"w") as z:
        for path in pins.PINNED_PUBLIC_MODULE_BLOBS:
            raw=(b"tamper" if path=="stocklens/paper.py"
                 else (root/path).read_bytes())
            z.writestr(path,raw)
    with pytest.raises(RuntimeError,match="DEPLOYED_ECONOMIC_CODE_DRIFT"):
        d.package(buf.getvalue(),root)



def test_realistic_deployed_binary_member_larger_than_30mb_is_allowed():
    """Regression for CloudShell UNEXPECTED_ZIP_MEMBER_SIZE before AWS writes."""
    root=Path(__file__).resolve().parents[1]
    buf=BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name in pins.PINNED_PUBLIC_MODULE_BLOBS:
            z.writestr(name,(root/name).read_bytes())
        # Legitimate but compressible vendored binary of 31+ MiB.
        z.writestr("vendor/large_numeric_module.so",b"\0"*31_000_001)
    result=d.package(buf.getvalue(),root)
    with zipfile.ZipFile(BytesIO(result)) as z:
        member=z.getinfo("vendor/large_numeric_module.so")
        assert member.file_size==31_000_001
        assert z.testzip() is None
        assert "infra/aws/sl63_epoch4_lambda.py" in z.namelist()


def test_hard_unzipped_250mib_package_limit_is_never_removed():
    from types import SimpleNamespace
    extra={"infra/aws/new.py":b"x"*2}
    with pytest.raises(RuntimeError,
                       match="DARK_LAMBDA_UNZIPPED_250MIB_LIMIT_EXCEEDED"):
        d.assert_uncompressed_budget([
            SimpleNamespace(filename="vendor/a.so",file_size=200*1024*1024,
                            is_dir=lambda:False),
            SimpleNamespace(filename="vendor/b.so",file_size=60*1024*1024,
                            is_dir=lambda:False),
        ],extra)
    with pytest.raises(RuntimeError,match="DARK_ZIP_MEMBER_COUNT_OR_SIZE_INVALID"):
        d.assert_uncompressed_budget([
            SimpleNamespace(filename="vendor/a.so",file_size=-1,
                            is_dir=lambda:False),
        ],extra)


def test_no_false_positive_for_at_most_250mib_total():
    from types import SimpleNamespace
    items=[SimpleNamespace(filename="pandas/_lib/large.so",
                           file_size=40*1024*1024,is_dir=lambda:False)]
    report=d.assert_uncompressed_budget(items,{"infra/aws/new.py":b"abc"})
    assert report["uncompressed_bytes"]==40*1024*1024+3
    assert report["largest_existing_member_bytes"]==40*1024*1024
