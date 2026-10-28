"""Fail-closed contracts for the opt-in StockLens PROD/ST isolation plan."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

SCRIPT=Path("infra/aws/provision_isolated_prod_st.sh")


def test_shell_syntax_and_no_deployment_on_import():
    proc=subprocess.run(["bash","-n",str(SCRIPT)],capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr


def test_separate_stacks_no_legacy_mutations_or_broker():
    code=SCRIPT.read_text()
    assert "SOURCE=stocklens-independent-staging" in code
    assert "ST=stocklens-st" in code
    assert "PROD=stocklens-prod" in code
    assert "stocklens-paper" not in code
    assert "CREATE_TWO_ISOLATED_STOCKLENS_ENVIRONMENTS" in code
    assert "read -r -p" in code
    assert "--change-set-type CREATE" in code
    assert "REFUSE_UPDATE_CHANGE_SET" in code
    assert "REFUSE_NON_ADDITIVE_CHANGE_SET" in code
    assert "ParameterKey=CandidateSignalScheduleState,ParameterValue=DISABLED" in code
    assert "ParameterKey=ExpectedSchedulerState,ParameterValue=DISABLED" in code
    assert "ParameterKey=MonitoringStartSession,ParameterValue=" in code
    assert "ParameterKey=AlertEmail,ParameterValue=" in code
    assert "REFUSE_EXISTING_TARGET" in code
    assert "REVIEW_IN_PROGRESS" in code
    assert "SOURCE_ARTIFACT" not in code or "ARTIFACT_PIN:" in code
    assert "DEPLOYED_LAMBDA_CODE_SHA_DIFFERS_FROM_SOURCE_ARTIFACT" in code
    assert "EXISTING_COST_ALERT_BUDGET_UNVERIFIED" in code
    assert "aws cloudformation delete-stack" not in code
    assert "aws events enable-rule" not in code
    assert "aws s3 rm" not in code
    assert "aws lambda invoke" not in code
    assert "broker" not in code.lower() or "NO_BROKER" in code


def fake_aws(tmp_path):
    fake=tmp_path/"aws"
    fake.write_text("""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$TRACE"
if [[ "$1" == sts && "$2" == get-caller-identity ]]; then
  echo "$FAKE_ACCOUNT"; exit 0
fi
if [[ "$1" == cloudformation && "$2" == describe-stacks ]]; then
  if [[ "$*" == *stocklens-prod* || "$*" == *stocklens-st* && "$*" != *stocklens-independent-staging* ]]; then
    exit 254
  fi
  if [[ "$*" == *StackStatus* ]];then echo CREATE_COMPLETE;exit 0;fi
  case "$*" in
    *CandidateDataBucket*) echo stocklens-data-source ;;
    *CandidateFunctionName*) echo stocklens-source-candidate ;;
    *CandidatePaperFunctionName*) echo stocklens-source-paper ;;
    *CandidatePaperOnlyRuleName*) echo stocklens-source-paper-rule ;;
    *CandidateOrchestratorRuleName*) echo stocklens-source-combined-rule ;;
    *CandidateSignalOnlyRuleName*) echo stocklens-source-signal-rule ;;
    *) echo None ;;
  esac
  exit 0
fi
if [[ "$1" == lambda && "$2" == get-function-configuration ]];then echo abc123;exit 0;fi
if [[ "$1" == events && "$2" == describe-rule ]];then echo DISABLED;exit 0;fi
echo "FORBIDDEN_MOCK_CALL:$*" >&2;exit 89
""")
    fake.chmod(0o755)
    return fake


def test_inspect_is_read_only_and_reports_two_missing_envs(tmp_path):
    fake_aws(tmp_path)
    trace=tmp_path/"calls.txt"
    env={**os.environ,"PATH":str(tmp_path)+os.pathsep+os.environ["PATH"],
         "TRACE":str(trace),"FAKE_ACCOUNT":"634740393398"}
    r=subprocess.run(["bash",str(SCRIPT),"inspect"],env=env,text=True,capture_output=True)
    assert r.returncode==0,r.stdout+r.stderr
    assert "MISSING_ENV:stocklens-prod" in r.stdout
    assert "MISSING_ENV:stocklens-st" in r.stdout
    assert "READ_ONLY_NO_AWS_MUTATIONS" in r.stdout
    calls=trace.read_text()
    assert "create-change-set" not in calls
    assert "execute-change-set" not in calls
    assert "update-stack" not in calls


def test_wrong_account_refuses_before_any_cloudformation_call(tmp_path):
    fake_aws(tmp_path)
    trace=tmp_path/"calls.txt"
    env={**os.environ,"PATH":str(tmp_path)+os.pathsep+os.environ["PATH"],
         "TRACE":str(trace),"FAKE_ACCOUNT":"000000000000"}
    r=subprocess.run(["bash",str(SCRIPT),"inspect"],env=env,text=True,capture_output=True)
    assert r.returncode!=0
    assert "WRONG_ACCOUNT" in r.stderr
    assert "cloudformation" not in trace.read_text()


def test_unknown_mode_refuses_early(tmp_path):
    fake_aws(tmp_path)
    env={**os.environ,"PATH":str(tmp_path)+os.pathsep+os.environ["PATH"]}
    r=subprocess.run(["bash",str(SCRIPT),"erase"],env=env,text=True,capture_output=True)
    assert r.returncode!=0
    assert "USAGE" in r.stdout
