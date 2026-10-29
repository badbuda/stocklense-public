#!/usr/bin/env bash
# StockLens ST-only: audit or activate the Signal-only scheduler.
# No PROD, Paper, orchestrator, brokerage or historical backfill operations.
set -euo pipefail
export AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1 AWS_PAGER=""
ACCOUNT=634740393398
STACK=stocklens-st
BUCKET=stocklens-st-candidatedata-6jj7i9fxjmfr
MODE="${1:-inspect}"
[[ "$MODE" == inspect || "$MODE" == activate ]] || { echo "USAGE: $0 inspect|activate"; exit 2; }
for x in aws python3; do command -v "$x" >/dev/null || { echo "MISSING:$x"; exit 2; }; done
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || { echo WRONG_ACCOUNT; exit 3; }
status="$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text)"
[[ "$status" == CREATE_COMPLETE || "$status" == UPDATE_COMPLETE ]] || { echo "ST_STACK_UNHEALTHY:$status"; exit 3; }
out() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue|[0]" --output text; }
[[ "$(out CandidateDataBucket)" == "$BUCKET" ]] || { echo WRONG_ST_BUCKET; exit 3; }
[[ "$(aws s3api get-bucket-versioning --bucket "$BUCKET" --query Status --output text)" == Enabled ]] || { echo VERSIONING_OFF; exit 3; }
[[ "$(aws s3api get-public-access-block --bucket "$BUCKET" --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' --output text)" == $'True\tTrue\tTrue\tTrue' ]] || { echo PUBLIC_BLOCK_MISSING; exit 3; }
for key in CandidateSignalOnlyRuleName CandidatePaperOnlyRuleName CandidateOrchestratorRuleName; do
  rule="$(out "$key")"
  [[ -n "$rule" && "$rule" != None ]] || { echo "MISSING_RULE:$key"; exit 3; }
  state="$(aws events describe-rule --name "$rule" --query State --output text)"
  case "$key:$state" in
    CandidateSignalOnlyRuleName:DISABLED|CandidateSignalOnlyRuleName:ENABLED|CandidatePaperOnlyRuleName:DISABLED|CandidateOrchestratorRuleName:DISABLED) ;;
    *) echo "UNSAFE_RULE_STATE:$key:$state";exit 3;;
  esac
  echo "RULE:$key:$state"
done
SIGNAL_RULE="$(out CandidateSignalOnlyRuleName)"
SIGNAL_FN="$(out CandidateFunctionName)"
[[ "$(aws events describe-rule --name "$SIGNAL_RULE" --query ScheduleExpression --output text)" == 'cron(30 2 ? * TUE-SAT *)' ]] || { echo WRONG_SIGNAL_CRON; exit 3; }
[[ "$(aws lambda get-function-configuration --function-name "$SIGNAL_FN" --query State --output text)" == Active ]] || { echo SIGNAL_LAMBDA_INACTIVE; exit 3; }
[[ "$(aws lambda get-function-configuration --function-name "$SIGNAL_FN" --query Handler --output text)" == infra.aws.independent_pipeline.handler ]] || { echo WRONG_SIGNAL_HANDLER; exit 3; }
[[ "$(aws lambda get-function-configuration --function-name "$SIGNAL_FN" --query 'Environment.Variables.STOCKLENS_DATA_BUCKET' --output text)" == "$BUCKET" ]] || { echo SIGNAL_WRONG_BUCKET; exit 3; }
ARN="$(aws lambda get-function-configuration --function-name "$SIGNAL_FN" --query FunctionArn --output text)"
TARGETS="$(aws events list-targets-by-rule --rule "$SIGNAL_RULE" --query 'Targets[].Arn' --output text)"
[[ "$TARGETS" == "$ARN" ]] || { echo "WRONG_SIGNAL_TARGET:$TARGETS";exit 3; }
TOPIC="$(out CandidateAlertsTopic)"
[[ -n "$TOPIC" && "$TOPIC" != None && "$TOPIC" == arn:aws:sns:eu-central-1:${ACCOUNT}:* ]] || { echo WRONG_ALERT_TOPIC;exit 3; }
SUBS="$(aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" --query "Subscriptions[?Protocol=='email' && SubscriptionArn!='PendingConfirmation'].SubscriptionArn" --output text)"
LIMIT="$(aws budgets describe-budget --region us-east-1 --account-id "$ACCOUNT" --budget-name StockLens-Whole-Account-20USD --query 'Budget.BudgetLimit.Amount' --output text)"
python3 - "$LIMIT" <<'PY'
from decimal import Decimal
import sys
x=Decimal(sys.argv[1])
if not (Decimal('0')<x<=Decimal('20')):raise SystemExit('BUDGET_ALERT_MISSING_OR_OVER_20')
PY
for prefix in signals/ paper/book/ paper/sessions/ paper/continuity/; do
  count="$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "$prefix" --query KeyCount --output text)"
  echo "S3:$prefix:$count"
done
MARKER=monitoring/signal-only-activation.json
if aws s3api head-object --bucket "$BUCKET" --key "$MARKER" >/dev/null 2>&1; then
  ANCHOR=PRESENT
else
  # HeadObject can return 403 for missing ListBucket permission: require ListObjects successful above.
  ANCHOR=ABSENT
fi
echo "SIGNAL_ACTIVATION_ANCHOR:$ANCHOR"
if [[ -z "$SUBS" || "$SUBS" == None ]]; then
  echo "BLOCKED_ST_SNS_UNCONFIRMED:topic=$TOPIC"
  echo "To enable signals, subscribe and confirm an email on ST's SNS topic, then rerun."
  exit 4
fi
echo "ST_SNS_CONFIRMED_SUBSCRIPTION:PRESENT (delivery still requires human-observed test)"
if [[ "$MODE" == inspect ]]; then
  echo "ST_SIGNAL_READINESS_INSPECT_PASS:NO_WRITES_NO_LAMBDA_INVOKES"
  exit 0
fi
[[ "$(aws events describe-rule --name "$SIGNAL_RULE" --query State --output text)" == DISABLED ]] || { echo SIGNAL_ALREADY_ACTIVE_OR_CHANGED;exit 3; }
[[ "$ANCHOR" == ABSENT ]] || { echo "PARTIAL_ACTIVATION_ANCHOR_PRESENT_REVIEW_FIRST";exit 3; }
printf '%s\n' 'Confirm you received a REAL alert sent through ST CloudWatch -> SNS email.'
read -r -p 'Type RECEIVED_ST_CLOUDWATCH_ALARM_EMAIL to activate Signal-only in ST: ' ACK
[[ "$ACK" == RECEIVED_ST_CLOUDWATCH_ALARM_EMAIL ]] || { echo NO_CONSENT_NO_WRITES;exit 4; }
TEMP="$(mktemp)"
trap 'rm -f "$TEMP"' EXIT
printf '%s' '{"schema":"STOCKLENS_STAGING_SIGNAL_MONITOR_V1"}' > "$TEMP"
aws s3api put-object --bucket "$BUCKET" --key "$MARKER" --body "$TEMP" --if-none-match '*' --content-type application/json >/dev/null
VER="$(aws s3api head-object --bucket "$BUCKET" --key "$MARKER" --query VersionId --output text)"
[[ -n "$VER" && "$VER" != None && "$VER" != null ]] || { echo ANCHOR_READBACK_FAILED_REVIEW_PARTIAL_STATE;exit 4; }
aws events enable-rule --name "$SIGNAL_RULE"
[[ "$(aws events describe-rule --name "$SIGNAL_RULE" --query State --output text)" == ENABLED ]] || { echo ENABLE_RULE_NOT_CONFIRMED;exit 4; }
for key in CandidatePaperOnlyRuleName CandidateOrchestratorRuleName; do
  [[ "$(aws events describe-rule --name "$(out "$key")" --query State --output text)" == DISABLED ]] || { echo "UNSAFE_RULE_STATE_CHANGED:$key";exit 5; }
done
echo "ST_SIGNAL_ONLY_ENABLED:anchor_version=$VER:NO_PAPER_NO_PROD_NO_BROKER"
