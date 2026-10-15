#!/usr/bin/env bash
# Operator-confirmed FIRST prospective Paper book creation in isolated staging.
# Mutates versioned S3 Paper receipts and Genesis; NEVER brokerage or production.
# Requires a successful least-privilege READ-ONLY dry-run of the same session.
# Usage: bash infra/aws/bootstrap_staging_paper_once.sh YYYY-MM-DD
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
STACK=stocklens-independent-staging
[[ "$REGION" == eu-central-1 ]] || { echo "REFUSE_NON_STAGING_REGION" >&2; exit 2; }
[[ "$#" == 1 ]] || { echo "Usage: $0 YYYY-MM-DD" >&2; exit 2; }
SESSION="$1"
python3 - "$SESSION" <<'PY'
import sys
from datetime import date
date_value=date.fromisoformat(sys.argv[1])
if date_value.isoformat()!=sys.argv[1]:
    raise SystemExit("INVALID_BOOTSTRAP_SESSION_DATE")
PY
# Verify AWS cost budget, independent Signal-only rule, confirmed SNS recipient
# and disarmed combined and Paper-only rules. Actual email delivery is an
# operator-observed precondition (this program cannot read the mailbox).
bash infra/aws/enable_staging_signal_only.sh check

output() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue|[0]" --output text
}
signal_rule="$(output CandidateSignalOnlyRuleName)"
paper_rule="$(output CandidatePaperOnlyRuleName)"
combined_rule="$(output CandidateOrchestratorRuleName)"
paper_fn="$(output CandidatePaperFunctionName)"
bucket="$(output CandidateDataBucket)"
[[ "$paper_fn" == "$STACK-paper-candidate" ]] || {
  echo "MISSING_ISOLATED_STAGING_PAPER_LAMBDA" >&2; exit 3;
}
[[ "$(aws events describe-rule --region "$REGION" --name "$signal_rule" --query State --output text)" == ENABLED ]] || {
  echo "REQUIRE_PROSPECTIVE_SIGNAL_SCHEDULE_ENABLED_FIRST" >&2; exit 3;
}
for rule in "$paper_rule" "$combined_rule"; do
  [[ "$(aws events describe-rule --region "$REGION" --name "$rule" --query State --output text)" == DISABLED ]] || {
    echo "REFUSE_ACTIVE_PAPER_SCHEDULE_BEFORE_FIRST_GENESIS" >&2; exit 3;
  }
done

# This invokes a SEPARATELY IAM READ-ONLY Lambda, verifies actual prior and
# current S3 server timestamps, and calculates observed-minute model equity.
bash infra/aws/accept_independent_paper_preflight.sh "$SESSION"

read -r -p 'Type CREATE_PROSPECTIVE_STAGING_PAPER_GENESIS to commit ONLY the Staging Paper book: ' approval
[[ "$approval" == CREATE_PROSPECTIVE_STAGING_PAPER_GENESIS ]] || {
  echo "PAPER_BOOTSTRAP_NOT_APPROVED_NO_WRITES" >&2; exit 3;
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '{"mode":"STAGING_PAPER_ONLY","expected_session":"%s","bootstrap":true}' "$SESSION" > "$tmp/request.json"
aws lambda invoke --region "$REGION" --function-name "$paper_fn" \
  --cli-binary-format raw-in-base64-out --payload "fileb://$tmp/request.json" \
  "$tmp/response.json" > "$tmp/meta.json"
python3 - "$SESSION" "$tmp/meta.json" "$tmp/response.json" <<'PY'
import json,sys
day,m,r=sys.argv[1:]
with open(m) as f: meta=json.load(f)
with open(r) as f: report=json.load(f)
if meta.get("StatusCode")!=200 or meta.get("FunctionError"):
    raise SystemExit("STAGING_FIRST_PAPER_BOOTSTRAP_FAILURE_REVIEW_PARTIAL_S3_STATE:"+str(report)[:1000])
if (report.get("status")!="STAGED_PAPER_VERIFIED" or report.get("session")!=day or
    report.get("broker_fills") is not False or report.get("broker_orders") is not False or
    report.get("audit")!="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"):
    raise SystemExit("UNEXPECTED_BOOTSTRAP_AUDIT_FAIL_REVIEW_PARTIAL_S3_STATE")
if not report.get("paper_version_id") or not report.get("paper_sha256"):
    raise SystemExit("MISSING_PAPER_VERSION_OR_SHA")
print("PROSPECTIVE_STAGING_PAPER_FIRST_RECEIPT_ARCHIVED:"+day+
      ":continuity="+str(report["continuity_status"])+
      ":equity="+str(report["equity"]))
print("NO_BROKER_ORDERS_OR_FILLS:NO_PRODUCTION_CHANGE")
PY

genesis_key="paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json"
version="$(aws s3api head-object --region "$REGION" --bucket "$bucket" \
  --key "$genesis_key" --query VersionId --output text)"
[[ -n "$version" && "$version" != None && "$version" != null ]] || {
  echo "GENESIS_NOT_COMMITTED_AFTER_PAPER_RECEIPT_HALT" >&2; exit 4;
}
printf '{"mode":"STAGING_PAPER_SCHEDULE_READINESS","expected_session":"%s","bootstrap":false}' "$SESSION" > "$tmp/check.json"
aws lambda invoke --region "$REGION" --function-name "$paper_fn" \
  --cli-binary-format raw-in-base64-out --payload "fileb://$tmp/check.json" \
  "$tmp/checked.json" > "$tmp/checkmeta.json"
python3 - "$SESSION" "$tmp/checkmeta.json" "$tmp/checked.json" <<'PY'
import json,sys
day,mp,rp=sys.argv[1:]
with open(mp) as f: meta=json.load(f)
with open(rp) as f: p=json.load(f)
if meta.get("FunctionError") or meta.get("StatusCode")!=200 or \
   p.get("status")!="STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY" or p.get("session")!=day or \
   p.get("broker_actions") is not False or p.get("paper_data_written") is not False or \
   p.get("chain_sessions",0)<1:
    raise SystemExit("GENESIS_COMMIT_NOT_VALIDATED_REVIEW_S3_NO_REBOOTSTRAP")
print("FIRST_PAPER_GENESIS_AND_FULL_CHAIN_VERIFIED:"+day)
print("AUTOMATIC_PAPER_SCHEDULE_REMAINS_DISABLED_UNTIL_LATER_OPT_IN")
PY
