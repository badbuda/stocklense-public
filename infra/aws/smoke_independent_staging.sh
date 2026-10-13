#!/usr/bin/env bash
# Explicit import-only smoke calls; no market requests, S3 writes or broker actions.
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
STACK=stocklens-independent-staging
[[ "$REGION" == eu-central-1 ]] || { echo "WRONG_REGION" >&2; exit 2; }
for tool in aws python3; do
  command -v "$tool" >/dev/null || { echo "MISSING_TOOL:$tool" >&2; exit 2; }
done
status="$(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text)"
[[ "$status" == CREATE_COMPLETE || "$status" == UPDATE_COMPLETE ]] || {
  echo "STACK_NOT_COMPLETE:$status" >&2; exit 2;
}
bucket="$(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidateDataBucket'].OutputValue|[0]" \
  --output text)"
rule="$(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidateOrchestratorRuleName'].OutputValue|[0]" \
  --output text)"
[[ -n "$bucket" && "$bucket" != None && -n "$rule" && "$rule" != None ]] || {
  echo "STAGING_OUTPUTS_MISSING" >&2; exit 2;
}
rule_state="$(aws events describe-rule --region "$REGION" --name "$rule" \
  --query State --output text)"
[[ "$rule_state" == DISABLED ]] || {
  echo "UNSAFE_SCHEDULE_STATE:$rule_state" >&2; exit 2;
}
signal_rule="$(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidateSignalOnlyRuleName'].OutputValue|[0]" \
  --output text)"
[[ -n "$signal_rule" && "$signal_rule" != None ]] || {
  echo "SIGNAL_ONLY_RULE_OUTPUT_MISSING" >&2; exit 2;
}
signal_rule_state="$(aws events describe-rule --region "$REGION" --name "$signal_rule" \
  --query State --output text)"
[[ "$signal_rule_state" == DISABLED ]] || {
  echo "SIGNAL_ONLY_NOT_SAFE_BY_DEFAULT:$signal_rule_state" >&2; exit 2;
}
versioning="$(aws s3api get-bucket-versioning --region "$REGION" \
  --bucket "$bucket" --query Status --output text)"
[[ "$versioning" == Enabled ]] || { echo "S3_VERSIONING_NOT_ENABLED" >&2; exit 2; }
block="$(aws s3api get-public-access-block --region "$REGION" \
  --bucket "$bucket" \
  --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' \
  --output text)"
[[ "$block" == $'True\tTrue\tTrue\tTrue' ]] || {
  echo "S3_PUBLIC_ACCESS_BLOCK_NOT_COMPLETE:$block" >&2; exit 2;
}
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
for component in signal paper orchestrator watchdog; do
  case "$component" in
    signal)
      fn="$STACK-candidate"
      expected_handler=infra.aws.independent_pipeline.handler
      ;;
    paper)
      fn="$STACK-paper-candidate"
      expected_handler=infra.aws.independent_paper.handler
      ;;
    orchestrator)
      fn="$STACK-orchestrator-candidate"
      expected_handler=infra.aws.independent_orchestrator.handler
      ;;
    watchdog)
      fn="$STACK-session-watchdog"
      expected_handler=infra.aws.independent_session_watchdog.handler
      ;;
  esac
  config="$(aws lambda get-function-configuration --region "$REGION" \
    --function-name "$fn" --query '[State,Runtime,Handler]' --output text)"
  expected_config="Active	python3.12	$expected_handler"
  [[ "$config" == "$expected_config" ]] || {
    echo "LAMBDA_CONFIG_NOT_READY:$component:$config" >&2; exit 3;
  }
  meta="$TMP_DIR/$component-meta.json"
  body="$TMP_DIR/$component-body.json"
  if ! aws lambda invoke --region "$REGION" \
    --function-name "$fn" \
    --invocation-type RequestResponse \
    --cli-binary-format raw-in-base64-out \
    --payload '{"mode":"STAGING_IMPORT_SMOKE"}' \
    "$body" >"$meta"; then
    echo "SMOKE_INVOKE_FAILED:$component" >&2; exit 3;
  fi
  if ! python3 - "$component" "$meta" "$body" <<'PY'
import json
import sys
name = sys.argv[1]
with open(sys.argv[2], encoding="utf-8") as handle:
    meta = json.load(handle)
with open(sys.argv[3], encoding="utf-8") as handle:
    response = json.load(handle)
expected = {"status": "STAGING_IMPORT_OK", "component": name,
            "broker_actions": False, "market_data_written": False}
if meta.get("StatusCode") != 200 or meta.get("FunctionError"):
    print(f"SMOKE_LAMBDA_RUNTIME_FAILURE:{name}:{meta.get('FunctionError')}")
    sys.exit(1)
if not all(response.get(k) == v for k, v in expected.items()):
    print(f"SMOKE_UNEXPECTED_RESPONSE:{name}:{str(response)[:600]}")
    sys.exit(1)
print(f"SMOKE_PASS:{name}:runtime-imports-ok:no-market-writes:no-broker")
PY
  then
    echo "LAMBDA_SMOKE_FAILED:$component; runtime excerpt follows:" >&2
    head -c 1600 "$body" >&2
    echo >&2
    exit 3
  fi
done
echo "PASS_STAGING_INFRA_AND_IMPORTS:stack=$STACK:rule=DISABLED:S3=PRIVATE_VERSIONED"
echo "NOT_PROVEN:market-session-source-parity-or-real-paper-receipts"
