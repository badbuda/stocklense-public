#!/usr/bin/env bash
# Read-only prospective Paper Bootstrap preflight in isolated AWS staging.
# Downloads observed market data; DOES NOT create a Paper book or write S3.
# Usage: bash infra/aws/accept_independent_paper_preflight.sh YYYY-MM-DD
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
STACK="stocklens-independent-staging"
[[ "$REGION" == eu-central-1 ]] || { echo "REFUSE_NON_STAGING_REGION" >&2; exit 2; }
[[ "$#" == 1 ]] || { echo "Usage: $0 YYYY-MM-DD" >&2; exit 2; }

python3 - "$1" <<'PY'
from datetime import date
import sys
session = sys.argv[1]
try:
    requested = date.fromisoformat(session)
except ValueError:
    raise SystemExit("INVALID_SESSION_DATE")
if session != requested.isoformat():
    raise SystemExit("NON_CANONICAL_SESSION_DATE")
# The Lambda validates the real XNYS close and next market open with
# exchange_calendars; do not reject the following morning in Israel here.
# This script only validates canonical input and the disabled orchestrator.
PY

stack_status="$(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text)"
[[ "$stack_status" == CREATE_COMPLETE || "$stack_status" == UPDATE_COMPLETE ]] || {
  echo "STAGING_STACK_NOT_COMPLETE:$stack_status" >&2; exit 3;
}
rule="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidateOrchestratorRuleName'].OutputValue|[0]" \
  --output text)"
[[ -n "$rule" && "$rule" != None ]] || { echo "NO_STAGING_ORCHESTRATOR_OUTPUT" >&2; exit 3; }
[[ "$(aws events describe-rule --region "$REGION" --name "$rule" --query State --output text)" == DISABLED ]] || {
  echo "REFUSE_ACTIVE_PAPER_ORCHESTRATOR" >&2; exit 3;
}

# Never invoke the mutable Paper Lambda from the read-only preflight CLI.
# Verify the CloudFormation-declared function, isolated role AND handler.
preflight_fn="$(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidatePaperPreflightFunctionName'].OutputValue|[0]" \
  --output text)"
role_name="$(aws cloudformation describe-stack-resource --region "$REGION" \
  --stack-name "$STACK" --logical-resource-id CandidatePaperPreflightRole \
  --query 'StackResourceDetail.PhysicalResourceId' --output text)"
[[ -n "$preflight_fn" && "$preflight_fn" != None && -n "$role_name" && "$role_name" != None ]] || {
  echo "MISSING_DEDICATED_READ_ONLY_PREFLIGHT" >&2; exit 3;
}
[[ "$preflight_fn" == "$STACK-paper-preflight" ]] || {
  echo "UNEXPECTED_PREFLIGHT_FUNCTION:$preflight_fn" >&2; exit 3;
}
function_handler="$(aws lambda get-function-configuration --region "$REGION" \
  --function-name "$preflight_fn" --query Handler --output text)"
function_role="$(aws lambda get-function-configuration --region "$REGION" \
  --function-name "$preflight_fn" --query Role --output text)"
[[ "$function_handler" == "infra.aws.independent_paper.preflight_handler" \
   && "${function_role##*/}" == "$role_name" ]] || {
  echo "PREFLIGHT_LAMBDA_ROLE_OR_HANDLER_MISMATCH" >&2; exit 3;
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
python3 - "$1" "$tmp/request.json" <<'PY'
import json,sys
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump({"mode":"STAGING_PAPER_BOOTSTRAP_PREFLIGHT",
               "expected_session":sys.argv[1]}, f)
PY
aws lambda invoke --region "$REGION" \
  --function-name "$preflight_fn" \
  --cli-binary-format raw-in-base64-out \
  --payload "fileb://$tmp/request.json" \
  "$tmp/response.json" >"$tmp/invoke.json"

python3 - "$1" "$tmp/invoke.json" "$tmp/response.json" <<'PY'
import json, sys
date, invoke_path, response_path = sys.argv[1:]
with open(invoke_path) as f: invoke = json.load(f)
with open(response_path) as f: result = json.load(f)
if invoke.get("StatusCode") != 200 or invoke.get("FunctionError"):
    raise SystemExit("STAGING_PAPER_PREFLIGHT_FAILED:" + str(result)[:1200])
if result.get("status") != "STAGING_PAPER_BOOTSTRAP_PREFLIGHT_PASS_READ_ONLY" or result.get("session") != date:
    raise SystemExit("UNEXPECTED_PAPER_PREFLIGHT_RESULT")
for key in ("broker_actions","broker_orders","broker_fills",
            "market_data_written","paper_data_written","genesis_written",
            "prospective_bootstrap_authorized"):
    if result.get(key) is not False:
        raise SystemExit("UNSAFE_PAPER_PREFLIGHT_FLAG:" + key)
if result.get("paper_accounting_audit") != "PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS":
    raise SystemExit("PAPER_ACCOUNTING_AUDIT_FAILED")
for key in ("current_signal_s3_version_id","prior_signal_s3_version_id",
            "model_candidate_sha256"):
    if not result.get(key):
        raise SystemExit("PAPER_PREFLIGHT_MISSING_EVIDENCE:" + key)
print("STAGING_PAPER_PREFLIGHT_READ_ONLY_VERIFIED:" + date)
print("PRIOR_SIGNAL=" + result["prior_session"])
print("OBSERVED_MARKET_SOURCE=" + result["market_source"])
print("MODEL_EQUITY=" + str(result["paper_model_equity"]))
print("MODEL_TRADES=" + str(result["paper_model_trades"]))
print("BROKER_DISABLED:YES; PAPER_BOOTSTRAP_NOT_AUTHORIZED; NO_S3_WRITES")
PY
