#!/usr/bin/env bash
# Explicit, separately gated STAGING PAPER-ONLY schedule. No brokerage access.
# Usage: bash infra/aws/enable_staging_paper_only.sh check|activate YYYY-MM-DD
# YYYY-MM-DD is an already stored and verified *prospective* Paper session.
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
STACK="stocklens-independent-staging"
MODE="${1:-}"
SESSION="${2:-}"
[[ "$REGION" == eu-central-1 ]] || { echo "REFUSE_NON_STAGING_REGION" >&2; exit 2; }
[[ "$#" == 2 && ( "$MODE" == check || "$MODE" == activate ) ]] || {
  echo "Usage: $0 check|activate YYYY-MM-DD" >&2; exit 2;
}
python3 - "$SESSION" <<'PY'
from datetime import date
import sys
d=date.fromisoformat(sys.argv[1])
if d.isoformat()!=sys.argv[1]:
    raise SystemExit("NONCANONICAL_XNYS_SESSION_DATE")
PY

# The existing Signal-only readiness gate checks confirmed staging SNS email,
# the account-wide <=$20 budget, and disarmed combined/Paper schedulers.
bash infra/aws/enable_staging_signal_only.sh check
output() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue|[0]" --output text
}
signal_rule="$(output CandidateSignalOnlyRuleName)"
paper_rule="$(output CandidatePaperOnlyRuleName)"
orchestrator_rule="$(output CandidateOrchestratorRuleName)"
paper_fn="$(output CandidatePaperFunctionName)"
data_bucket="$(output CandidateDataBucket)"
[[ -n "$paper_rule" && "$paper_rule" != None && -n "$paper_fn" && "$paper_fn" != None && \
   -n "$data_bucket" && "$data_bucket" != None ]] || {
  echo "PAPER_ONLY_REQUIRED_STAGING_OUTPUTS_MISSING" >&2; exit 3;
}
[[ "$(aws events describe-rule --region "$REGION" --name "$signal_rule" \
  --query State --output text)" == ENABLED ]] || {
  echo "REQUIRE_AUTOMATED_SIGNAL_ENABLED_FIRST" >&2; exit 3;
}
[[ "$(aws events describe-rule --region "$REGION" --name "$orchestrator_rule" \
  --query State --output text)" == DISABLED ]] || {
  echo "REFUSE_DUPLICATE_COMBINED_ORCHESTRATOR" >&2; exit 3;
}
paper_state="$(aws events describe-rule --region "$REGION" --name "$paper_rule" \
  --query State --output text)"
[[ "$paper_state" == DISABLED || "$paper_state" == ENABLED ]] || {
  echo "UNEXPECTED_PAPER_RULE_STATE:$paper_state" >&2; exit 3;
}

# Re-run the full anchored Paper chain verifier on AWS with exact immutable S3
# server-time evidence, WITHOUT a brokerage order or any S3 write.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '{"mode":"STAGING_PAPER_SCHEDULE_READINESS","expected_session":"%s","bootstrap":false}' \
  "$SESSION" > "$tmp/request.json"
aws lambda invoke --region "$REGION" --function-name "$paper_fn" \
  --cli-binary-format raw-in-base64-out --payload "fileb://$tmp/request.json" \
  "$tmp/response.json" > "$tmp/meta.json"
python3 - "$SESSION" "$tmp/meta.json" "$tmp/response.json" <<'PY'
import json,sys
session,meta_path,data_path=sys.argv[1:]
with open(meta_path) as f: meta=json.load(f)
with open(data_path) as f: data=json.load(f)
if meta.get("StatusCode")!=200 or meta.get("FunctionError"):
    raise SystemExit("READ_ONLY_PAPER_SCHEDULE_GATE_FAILED:"+str(data)[:800])
if data.get("status")!="STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY" or data.get("session")!=session:
    raise SystemExit("UNEXPECTED_PAPER_SCHEDULE_READINESS")
for key in ("broker_actions","broker_orders","broker_fills","paper_data_written",
            "paper_automation_authorized","cross_vendor_parity_proven"):
    if data.get(key) is not False:
        raise SystemExit("UNSAFE_PAPER_SCHEDULE_READINESS_FLAG:"+key)
if data.get("continuity_status") not in ("ON_TIME_QUALIFIED","LATE_WITH_CONTEMPORANEOUS_EVIDENCE"):
    raise SystemExit("NONFORWARD_PAPER_CONTINUITY")
if not data.get("paper_version_id") or not data.get("paper_sha256") or data.get("chain_sessions",0)<1:
    raise SystemExit("MISSING_DURABLE_PAPER_CHAIN_EVIDENCE")
print("PAPER_AUTOMATION_CHAIN_GATE_PASS:date="+session+":verified_sessions="+str(data["chain_sessions"]))
print("NOTE:CROSS_VENDOR_PARITY_NOT_PROVEN:NO_BROKER_AND_STAGING_ONLY")
PY
if [[ "$MODE" == check ]]; then
  echo "CHECK_PASS_ONLY:no EventBridge state change; separate provider-parity gate remains external"
  exit 0
fi
if [[ "$paper_state" == ENABLED ]]; then
  echo "PAPER_ONLY_RULE_ALREADY_ENABLED"
  exit 0
fi
echo "This enables ONLY STAGING Paper after the 02:30 UTC frozen Signal." >&2
echo "External same-vendor drift and second-provider parity MUST be reviewed before approving." >&2
read -r -p 'Type REVIEWED_STAGING_PAPER_RISK_AND_EMAIL_ALERTS to enable: ' consent
[[ "$consent" == REVIEWED_STAGING_PAPER_RISK_AND_EMAIL_ALERTS ]] || {
  echo "PAPER_SCHEDULE_ACTIVATION_NOT_APPROVED" >&2; exit 3;
}
aws events enable-rule --region "$REGION" --name "$paper_rule"
[[ "$(aws events describe-rule --region "$REGION" --name "$paper_rule" \
  --query State --output text)" == ENABLED ]] || {
  echo "PAPER_SCHEDULE_ACTIVATION_NOT_CONFIRMED" >&2; exit 4;
}
echo "STAGING_PAPER_ONLY_SCHEDULE_ENABLED:broker_disabled:combined_orchestrator_disabled"
