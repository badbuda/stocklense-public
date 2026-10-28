#!/usr/bin/env bash
# Creates two IDENTICAL resource-isolated, initially DISARMED, paper-only stacks.
# inspect: READ ONLY. prepare: CREATE change sets, no resources.
# apply: manual typed approval; execute reviewed create-only change sets.
set -euo pipefail
export AWS_PAGER="" AWS_DEFAULT_REGION=eu-central-1 AWS_REGION=eu-central-1
ACCOUNT=634740393398
SOURCE=stocklens-independent-staging
ST=stocklens-st
PROD=stocklens-prod
CHANGE=stocklens-create-isolated-v1
if (( $# == 0 )); then MODE=inspect; else MODE="$1"; fi
[[ "$#" -le 1 ]] || { echo "USAGE: inspect|prepare|apply"; exit 2; }
case "$MODE" in inspect|prepare|apply) ;; *) echo "USAGE: inspect|prepare|apply";exit 2;; esac
for c in aws python3 sha256sum; do command -v "$c" >/dev/null || exit 2; done
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || {
  echo WRONG_ACCOUNT >&2; exit 3;
}
src_status="$(aws cloudformation describe-stacks --stack-name "$SOURCE"  --query 'Stacks[0].StackStatus' --output text)"
[[ "$src_status" == CREATE_COMPLETE || "$src_status" == UPDATE_COMPLETE ]] || {
 echo "SOURCE_STACK_NOT_STABLE:$src_status" >&2; exit 3;
}
output() {
 aws cloudformation describe-stacks --stack-name "$1"   --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue|[0]" --output text
}
exists() { aws cloudformation describe-stacks --stack-name "$1"  --query 'Stacks[0].StackStatus' --output text >/dev/null 2>&1; }
src_bucket="$(output "$SOURCE" CandidateDataBucket)"
src_signal="$(output "$SOURCE" CandidateFunctionName)"
src_paper="$(output "$SOURCE" CandidatePaperFunctionName)"
[[ -n "$src_bucket" && "$src_bucket" != None &&
   -n "$src_signal" && "$src_signal" != None &&
   -n "$src_paper" && "$src_paper" != None ]] || { echo SOURCE_OUTPUTS_MISSING; exit 3; }
signal_sha="$(aws lambda get-function-configuration --function-name "$src_signal" --query CodeSha256 --output text)"
paper_sha="$(aws lambda get-function-configuration --function-name "$src_paper" --query CodeSha256 --output text)"
[[ -n "$signal_sha" && "$signal_sha" != None && "$signal_sha" == "$paper_sha" ]] || {
 echo "SOURCE_LAMBDAS_DIFFERENT_CODE_PACKAGES_NO_IDENTICAL_CLONE" >&2;exit 3;
}
for rule_type in CandidatePaperOnlyRuleName CandidateOrchestratorRuleName; do
 rule="$(output "$SOURCE" "$rule_type")"
 [[ "$(aws events describe-rule --name "$rule" --query State --output text)" == DISABLED ]] || {
  echo SOURCE_PAPER_OR_ORCHESTRATOR_ACTIVE >&2;exit 3;
 }
done

if [[ "$MODE" == inspect ]]; then
 echo "EXISTING_SIGNAL_SOURCE:$SOURCE:source_data=$src_bucket:status=$src_status"
 for target in "$PROD" "$ST"; do
  if ! exists "$target"; then echo "MISSING_ENV:$target";continue;fi
  state="$(aws cloudformation describe-stacks --stack-name "$target"     --query 'Stacks[0].StackStatus' --output text)"
  bucket="$(output "$target" CandidateDataBucket)"
  fn="$(output "$target" CandidateFunctionName)"
  pn="$(output "$target" CandidatePaperFunctionName)"
  if [[ "$state" == REVIEW_IN_PROGRESS ]]; then
    echo "PENDING_REVIEW_NOT_DEPLOYED:$target"
    continue
  fi
  [[ "$state" == CREATE_COMPLETE || "$state" == UPDATE_COMPLETE ]] || {
    echo "ENV_UNHEALTHY:$target:$state" >&2;exit 4;
  }
  [[ -n "$bucket" && "$bucket" != None && "$bucket" != "$src_bucket" ]] || {
    echo "S3_ISOLATION_FAILED:$target" >&2;exit 4;
  }
  [[ "$(aws lambda get-function-configuration --function-name "$fn" --query CodeSha256 --output text)" == "$signal_sha" &&
     "$(aws lambda get-function-configuration --function-name "$pn" --query CodeSha256 --output text)" == "$paper_sha" ]] || {
    echo "SOURCE_ARTIFACT_PARITY_FAILED:$target" >&2;exit 4;
  }
  for rule_type in CandidateSignalOnlyRuleName CandidatePaperOnlyRuleName CandidateOrchestratorRuleName; do
   rule="$(output "$target" "$rule_type")"
   [[ "$(aws events describe-rule --name "$rule" --query State --output text)" == DISABLED ]] || {
     echo "UNAPPROVED_ACTIVE_SCHEDULE:$target:$rule_type" >&2;exit 4;
   }
  done
  echo "ISOLATION_PASS:$target:bucket=$bucket:runtime_parity=PASS:signal_paper_orchestrator=DISABLED"
 done
 echo "READ_ONLY_NO_AWS_MUTATIONS:NO_BROKER_ORDERS"
 exit 0
fi

# Neither an existing PROD nor an existing ST may be replaced or updated.
for target in "$PROD" "$ST"; do
 if [[ "$MODE" == prepare ]]; then
   if exists "$target"; then echo "REFUSE_EXISTING_TARGET:$target";exit 4;fi
 else
   # CFN CREATE change sets leave a REVIEW_IN_PROGRESS placeholder stack.
   state="$(aws cloudformation describe-stacks --stack-name "$target" \
       --query 'Stacks[0].StackStatus' --output text)"
   [[ "$state" == REVIEW_IN_PROGRESS ]] || {
     echo "REFUSE_NOT_REVIEW_ONLY_PLACEHOLDER:$target:$state" >&2;exit 4;
   }
 fi
done
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
aws cloudformation get-template --stack-name "$SOURCE"  --query TemplateBody --output text > "$work/source.yaml"
python3 - "$work/source.yaml" "$SOURCE" <<'PY'
import hashlib,pathlib,sys
data=pathlib.Path(sys.argv[1]).read_bytes()
txt=data.decode()
required=("AWSTemplateFormatVersion","AWS::StackName","CandidateData",
          "CandidateSignalScheduleState","MonitoringStartSession",
          "CandidatePaperPreflightLambda","CandidateSessionWatchdogLambda",
          "ArtifactBucket","ArtifactKey")
if not 10000 < len(data) < 51200 or any(x not in txt for x in required):
 raise SystemExit("SOURCE_TEMPLATE_NOT_EXPECTED_ISOLATED_FIVE_LAMBDA_INFRA")
if sys.argv[2] in txt:
 raise SystemExit("CANNOT_CLONE_HARD_CODED_SOURCE_STACK")
if any(x in txt for x in ("AWS::IAM::User","AWS::IAM::AccessKey")):
 raise SystemExit("UNSAFE_STATIC_IAM_RESOURCES")
print("PINNED_DEPLOYED_TEMPLATE_SHA256:"+hashlib.sha256(data).hexdigest())
PY
aws cloudformation validate-template --template-body "file://$work/source.yaml" >/dev/null
aws cloudformation describe-stacks --stack-name "$SOURCE"  --query 'Stacks[0].Parameters' --output json > "$work/params.json"
mapfile -t artifact < <(python3 - "$work/params.json" <<'PY'
import json,sys
x={v["ParameterKey"]:v["ParameterValue"] for v in json.load(open(sys.argv[1]))}
b,k=x.get("ArtifactBucket"),x.get("ArtifactKey")
if not b or not k or "latest" in k.lower(): raise SystemExit("NO_IMMUTABLE_DEPLOYED_ARTIFACT")
print(b);print(k)
PY
)
artifact_bucket="$(sed -n '1p' <<< "$(printf '%s\n' "${artifact[@]}")")"
artifact_key="$(sed -n '2p' <<< "$(printf '%s\n' "${artifact[@]}")")"
[[ -n "$artifact_bucket" && -n "$artifact_key" ]] || { echo NO_ARTIFACT;exit 4; }
aws s3api head-object --bucket "$artifact_bucket" --key "$artifact_key" >/dev/null
# Lambda CodeSha256 is base64(SHA256(exact deployed ZIP)). Reject a stale S3
# artifact key even if the CloudFormation parameter still points to it.
aws s3api get-object --bucket "$artifact_bucket" --key "$artifact_key" "$work/artifact.zip" >/dev/null
python3 - "$work/artifact.zip" "$signal_sha" <<'PY'
import base64,hashlib,pathlib,sys
actual=base64.b64encode(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).digest()).decode()
if actual!=sys.argv[2]:
 raise SystemExit("DEPLOYED_LAMBDA_CODE_SHA_DIFFERS_FROM_SOURCE_ARTIFACT")
print("IDENTICAL_PINNED_RUNTIME_SOURCE_VERIFIED")
PY
budget="$(aws budgets describe-budget --region us-east-1 --account-id "$ACCOUNT"  --budget-name StockLens-Whole-Account-20USD  --query 'Budget.BudgetLimit.Amount' --output text)"
python3 - "$budget" <<'PY'
from decimal import Decimal
import sys
try:
 assert Decimal("0") < Decimal(sys.argv[1]) <= Decimal("20")
except Exception:
 raise SystemExit("EXISTING_COST_ALERT_BUDGET_UNVERIFIED")
print("COST_ALERT_BUDGET_VERIFIED_NOT_HARD_CAP")
PY
echo "ARTIFACT_PIN:s3://$artifact_bucket/$artifact_key"
echo "COST:two_KMS_keys_plus_Lambda_CloudWatch_S3_SNS;budget_is_alert_only"
if [[ "$MODE" == prepare ]]; then
  for target in "$ST" "$PROD"; do
    echo "PREPARE_CREATE_ONLY:$target"
    aws cloudformation create-change-set --stack-name "$target"       --change-set-name "$CHANGE" --change-set-type CREATE       --template-body "file://$work/source.yaml"       --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM       --parameters       "ParameterKey=ArtifactBucket,ParameterValue=$artifact_bucket"       "ParameterKey=ArtifactKey,ParameterValue=$artifact_key"       "ParameterKey=AlertEmail,ParameterValue="       "ParameterKey=CandidateSignalScheduleState,ParameterValue=DISABLED"       "ParameterKey=ExpectedSchedulerState,ParameterValue=DISABLED"       "ParameterKey=MonitoringStartSession,ParameterValue="       --tags "Key=StockLensEnvironment,Value=$target"              "Key=StockLensSafety,Value=PAPER_ONLY_NO_BROKER" >/dev/null
    aws cloudformation wait change-set-create-complete --stack-name "$target" --change-set-name "$CHANGE"
    aws cloudformation describe-change-set --stack-name "$target" --change-set-name "$CHANGE"       --query 'Changes[].ResourceChange.[Action,LogicalResourceId,ResourceType]' --output table
  done
  echo "PREPARED_BOTH_CHANGE_SETS:NO_STACK_RESOURCES_CREATED"
  exit 0
fi
# apply may not generate its own change sets; change review must be separate.
for target in "$ST" "$PROD"; do
 aws cloudformation describe-change-set --stack-name "$target"    --change-set-name "$CHANGE" --output json > "$work/$target.json"
 python3 - "$work/$target.json" "$artifact_bucket" "$artifact_key" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
if x.get("Status")!="CREATE_COMPLETE" or x.get("ExecutionStatus")!="AVAILABLE":
 raise SystemExit("CHANGESET_NOT_READY")
if x.get("ChangeSetType")!="CREATE":raise SystemExit("REFUSE_UPDATE_CHANGE_SET")
cs=x.get("Changes",[])
if not cs or any(c.get("ResourceChange",{}).get("Action")!="Add" for c in cs):
 raise SystemExit("REFUSE_NON_ADDITIVE_CHANGE_SET")
params={p["ParameterKey"]:p.get("ParameterValue") for p in x.get("Parameters",[])}
expected={"ArtifactBucket":sys.argv[2],"ArtifactKey":sys.argv[3],
 "CandidateSignalScheduleState":"DISABLED","ExpectedSchedulerState":"DISABLED",
 "MonitoringStartSession":"","AlertEmail":""}
if any(params.get(k)!=v for k,v in expected.items()):
 raise SystemExit("CHANGE_SET_PARAMETERS_CHANGED")
types={c["ResourceChange"]["ResourceType"] for c in cs}
if not {"AWS::S3::Bucket","AWS::Lambda::Function"}<=types or types&{
 "AWS::IAM::User","AWS::IAM::AccessKey"}:
 raise SystemExit("UNSAFE_RESOURCE_TYPES")
print("CHANGE_SET_CREATE_ONLY_REVIEW_PASS:"+x["StackName"])
PY
done
read -r -p 'Confirm AWS resource costs. Type CREATE_TWO_ISOLATED_STOCKLENS_ENVIRONMENTS: ' approval
[[ "$approval" == CREATE_TWO_ISOLATED_STOCKLENS_ENVIRONMENTS ]] || {
 echo "NOT_APPROVED_NO_STACKS_CREATED";exit 4;
}
# Research ST first; a failure does not cause prod deployment or auto deletion.
for target in "$ST" "$PROD"; do
 echo "EXECUTE_REVIEWED_CHANGE_SET:$target"
 aws cloudformation execute-change-set --stack-name "$target" --change-set-name "$CHANGE"
 aws cloudformation wait stack-create-complete --stack-name "$target" || {
  echo "PARTIAL_DEPLOY_REQUIRES_MANUAL_REVIEW_NO_AUTO_DELETE:$target" >&2;exit 5;
 }
done
bash "$0" inspect
