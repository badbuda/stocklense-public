#!/usr/bin/env bash
# Explicit operator opt-in for STAGING SIGNAL ONLY, never Paper or broker.
# Usage: bash infra/aws/enable_staging_signal_only.sh check|activate
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
STACK=stocklens-independent-staging
MODE="${1:-check}"
[[ "$REGION" == eu-central-1 ]] || { echo "REFUSE_WRONG_REGION" >&2; exit 2; }
[[ "$#" -le 1 && ( "$MODE" == check || "$MODE" == activate ) ]] || {
  echo "Usage: bash infra/aws/enable_staging_signal_only.sh check|activate" >&2; exit 2;
}
for program in aws python3; do
  command -v "$program" >/dev/null || { echo "MISSING_COMMAND:$program" >&2; exit 2; }
done

account="$(aws sts get-caller-identity --query Account --output text)"
status="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK"   --query 'Stacks[0].StackStatus' --output text)"
[[ "$status" == CREATE_COMPLETE || "$status" == UPDATE_COMPLETE ]] || {
  echo "STAGING_NOT_COMPLETE:$status" >&2; exit 3;
}
stack_output() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK"     --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue|[0]" --output text
}
signal_rule="$(stack_output CandidateSignalOnlyRuleName)"
orchestrator_rule="$(stack_output CandidateOrchestratorRuleName)"
alerts_topic="$(stack_output CandidateAlertsTopic)"
[[ -n "$signal_rule" && "$signal_rule" != None && -n "$orchestrator_rule" &&    "$orchestrator_rule" != None && -n "$alerts_topic" && "$alerts_topic" != None ]] || {
  echo "MISSING_STAGING_OUTPUTS" >&2; exit 3;
}
# The combined Signal+Paper orchestrator must not accidentally activate.
orchestrator_state="$(aws events describe-rule --region "$REGION"   --name "$orchestrator_rule" --query State --output text)"
[[ "$orchestrator_state" == DISABLED ]] || {
  echo "PAPER_ORCHESTRATOR_NOT_DISABLED:$orchestrator_state" >&2; exit 3;
}
signal_state="$(aws events describe-rule --region "$REGION"   --name "$signal_rule" --query State --output text)"
[[ "$signal_state" == DISABLED || "$signal_state" == ENABLED ]] || {
  echo "INVALID_SIGNAL_RULE_STATE:$signal_state" >&2; exit 3;
}

# Existing Budget is whole-account alert-only; not a spending cap.
budget_limit="$(aws budgets describe-budget --region us-east-1   --account-id "$account" --budget-name StockLens-Whole-Account-20USD   --query 'Budget.BudgetLimit.Amount' --output text)"
python3 - "$budget_limit" <<'PY'
from decimal import Decimal
import sys
try:
    amount = Decimal(sys.argv[1])
    assert Decimal("0") < amount <= Decimal("20")
except Exception:
    raise SystemExit("REQUIRE_EXISTING_ACCOUNT_COST_BUDGET_MAX_20")
PY

# Only confirmed SNS email subscriptions count; not the account-wide Budget emails.
confirmed_email="$(aws sns list-subscriptions-by-topic --region "$REGION"   --topic-arn "$alerts_topic"   --query "Subscriptions[?Protocol=='email' && SubscriptionArn!='PendingConfirmation'].SubscriptionArn"   --output text)"
[[ -n "$confirmed_email" && "$confirmed_email" != None ]] || {
  echo "STAGING_SNS_EMAIL_UNCONFIRMED; subscribe, confirm, and test delivery first" >&2; exit 3;
}

echo "CHECK_PASS:staging=$STACK:combined_orchestrator=DISABLED:signal_only=$signal_state:budget_usd=$budget_limit:sns_email_confirmed=true"
echo "IMPORTANT:SNS subscription does not prove email delivery. Test a real alarm before activation."
echo "IMPORTANT:AWS Budgets is alert-only, not a hard spending cap."

if [[ "$MODE" == check ]]; then
  echo "NO_CHANGES_MADE: run with 'activate' only AFTER receiving a test alarm email."
  exit 0
fi
if [[ "$signal_state" == ENABLED ]]; then
  echo "ALREADY_ENABLED:signal-only staging rule; no action needed"
  exit 0
fi
printf 'Confirm real STAGING SNS alarm email delivery and no Paper/broker actions.\n' >&2
read -r -p 'Type RECEIVED_STAGING_ALARM_EMAIL to opt in: ' response
[[ "$response" == RECEIVED_STAGING_ALARM_EMAIL ]] || {
  echo "ACTIVATION_NOT_CONFIRMED; no changes" >&2; exit 3;
}
aws events enable-rule --region "$REGION" --name "$signal_rule"
[[ "$(aws events describe-rule --region "$REGION" --name "$signal_rule"   --query State --output text)" == ENABLED ]] || {
  echo "ACTIVATION_NOT_VERIFIED; inspect rule and alarms" >&2; exit 4;
}
[[ "$(aws events describe-rule --region "$REGION" --name "$orchestrator_rule"   --query State --output text)" == DISABLED ]] || {
  echo "UNSAFE_PAPER_ORCHESTRATOR_ENABLED" >&2; exit 4;
}
echo "STAGING_SIGNAL_ONLY_AUTOMATION_ENABLED:no_paper:no_broker:scheduled_after_ny_close"
echo "CloudFormation template intentionally defaults to DISABLED; any future stack redeploy may reset this opt-in. Recheck after every deploy."
