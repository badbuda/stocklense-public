"""End-to-end safe ST publication with a fully local mocked AWS CLI.

No real AWS, S3, HTTP, or broker access in these tests. Confirms that explicit
CLI consent works without any terminal reads, and 404/403 are differentiated.
"""
import os
from pathlib import Path
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra/aws/publish_st_sl9_031_results.sh"
KEY = "research/experiments/SL9-031/8fe5ebdb7f7e2d3a9bc6bc9109d2b2745aae9bea"


def setup_mocks(tmp_path, *, deny_head=False):
    bin_dir = tmp_path / "mockbin"
    bin_dir.mkdir()
    state = tmp_path / "s3"
    state.mkdir()
    aws = bin_dir / "aws"
    aws.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import os, sys, json, pathlib, shutil
        a=sys.argv[1:]
        root=pathlib.Path(os.environ["MOCK_S3_ROOT"])
        def arg(k):
            return a[a.index(k)+1]
        op=a[0:2]
        if op==["sts","get-caller-identity"]:
            print("634740393398")
        elif op==["cloudformation","describe-stacks"]:
            if "--query" in a and "StackStatus" in arg("--query"):
                print("CREATE_COMPLETE")
            else:
                logical=arg("--query").split("OutputKey=='",1)[1].split("'",1)[0]
                names={"CandidateDataBucket":"stocklens-st-candidatedata-6jj7i9fxjmfr"}
                print(names.get(logical,logical+"-mock-disabled"))
        elif op==["s3api","get-bucket-versioning"]:
            print("Enabled")
        elif op==["s3api","get-public-access-block"]:
            print(chr(9).join(["True"]*4))
        elif op==["events","describe-rule"]:
            print("DISABLED")
        elif op==["s3api","head-object"]:
            if os.getenv("MOCK_DENY_HEAD")=="1":
                print("An error occurred (403) when calling the HeadObject operation: Forbidden",file=sys.stderr)
                sys.exit(255)
            target=root / arg("--key")
            if not target.is_file():
                print("An error occurred (404) when calling the HeadObject operation: Not Found",file=sys.stderr)
                sys.exit(255)
            print("mock-version" if "--query" in a else json.dumps({"VersionId":"mock-version"}))
        elif op==["s3api","put-object"]:
            assert "--if-none-match" in a and arg("--if-none-match")=="*",a
            target=root / arg("--key")
            if target.exists():
                print("PreconditionFailed (412)",file=sys.stderr)
                sys.exit(255)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(arg("--body"),target)
            print(json.dumps({"VersionId":"mock-version"}))
        elif op==["s3api","get-object"]:
            target=root / arg("--key")
            assert target.is_file(),target
            shutil.copyfile(target,a[-3] if a[-2:]==["--output","json"] else a[-1])
            print(json.dumps({"VersionId":"mock-version"}))
        else:
            raise RuntimeError("UNEXPECTED_AWS_METHOD:"+str(a))
        """))
    aws.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import os,sys,shutil,pathlib
        args=sys.argv[1:]
        destination=args[args.index("--output")+1]
        url=args[args.index("--output")-1]
        name=url.rsplit("/",1)[-1]
        if name not in ("st-combo-results.json","st-combo-curves.csv"):
            raise RuntimeError("UNEXPECTED_CURL_SOURCE:"+name)
        shutil.copyfile(pathlib.Path(os.environ["MOCK_DOCS"])/name,destination)
        """))
    curl.chmod(0o755)
    env=os.environ.copy()
    env.update({
        "PATH":str(bin_dir)+os.pathsep+env["PATH"],
        "MOCK_S3_ROOT":str(state),
        "MOCK_DOCS":str(ROOT/"docs"),
        "MOCK_DENY_HEAD":"1" if deny_head else "0",
    })
    return env,state


def run(args,env,timeout=25):
    return subprocess.run(["bash",str(SCRIPT),*args],cwd=ROOT,env=env,
                          capture_output=True,text=True,timeout=timeout)


def test_one_line_mobile_confirmation_publishes_only_two_st_objects(tmp_path):
    env,state=setup_mocks(tmp_path)
    a=run(["publish","--confirm","PUBLISH_ST_RESEARCH_ONLY"],env)
    assert a.returncode==0,(a.stdout,a.stderr)
    assert "EXPLICIT_ST_ONLY_PUBLICATION_CONSENT_VERIFIED" in a.stdout
    assert "ST_S3_SL9_031_PUBLISH_AND_VERIFY_PASS" in a.stdout
    got=sorted(str(x.relative_to(state)) for x in state.rglob("*") if x.is_file())
    assert got==[KEY+"/curves.csv",KEY+"/results.json"]
    assert (state/KEY/"curves.csv").read_bytes()==(ROOT/"docs/st-combo-curves.csv").read_bytes()
    assert (state/KEY/"results.json").read_bytes()==(ROOT/"docs/st-combo-results.json").read_bytes()
    b=run(["publish","--confirm","PUBLISH_ST_RESEARCH_ONLY"],env)
    assert b.returncode==0,(b.stdout,b.stderr)
    assert b.stdout.count("EXISTING_PINNED_ST_OBJECT_REUSED:")==2
    assert run(["verify"],env).returncode==0


def test_partial_publication_resumes_without_overwrite(tmp_path):
    env,state=setup_mocks(tmp_path)
    assert run(["publish","--confirm","PUBLISH_ST_RESEARCH_ONLY"],env).returncode==0
    (state/KEY/"curves.csv").unlink()
    again=run(["publish","--confirm","PUBLISH_ST_RESEARCH_ONLY"],env)
    assert again.returncode==0,(again.stdout,again.stderr)
    assert "EXISTING_PINNED_ST_OBJECT_REUSED:" in again.stdout
    assert "CREATED_NEW_PINNED_ST_OBJECT:" in again.stdout


def test_conflicting_existing_s3_object_never_overwritten(tmp_path):
    env,state=setup_mocks(tmp_path)
    dest=state/KEY/"results.json"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"invalid-other-data")
    bad=run(["publish","--confirm","PUBLISH_ST_RESEARCH_ONLY"],env)
    assert bad.returncode!=0
    assert "AWS_ST_OBJECT_CONTENT_MISMATCH" in bad.stderr
    assert dest.read_bytes()==b"invalid-other-data"
    assert not (state/KEY/"curves.csv").exists()


def test_denied_head_is_not_misinterpreted_as_missing(tmp_path):
    env,state=setup_mocks(tmp_path,deny_head=True)
    bad=run(["publish","--confirm","PUBLISH_ST_RESEARCH_ONLY"],env)
    assert bad.returncode!=0
    assert "ST_S3_HEAD_DENIED_OR_UNKNOWN_NO_WRITE" in bad.stderr
    assert not list(state.rglob("*.json")) and not list(state.rglob("*.csv"))


def test_bad_or_absent_consent_cannot_create_any_s3_object(tmp_path):
    env,state=setup_mocks(tmp_path)
    for a in (["publish","--confirm","WRONG"],
              ["inspect","--confirm","PUBLISH_ST_RESEARCH_ONLY"],
              ["publish","--confirm"],
              ["publish","--confirm","PUBLISH_ST_RESEARCH_ONLY","extra"]):
        result=run(a,env)
        assert result.returncode!=0,(a,result.stdout,result.stderr)
        assert not list(state.rglob("*.json")) and not list(state.rglob("*.csv"))
    allowed=run(["inspect"],env)
    assert allowed.returncode==0,(allowed.stdout,allowed.stderr)
    assert "INSPECT_READ_ONLY_NO_AWS_MUTATIONS" in allowed.stdout
