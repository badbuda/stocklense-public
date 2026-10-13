#!/usr/bin/env bash
# Read-only AWS release evidence collection after the single staging deploy.
# NEVER sends alarms, changes schedules, writes Paper, or touches the broker.
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
STACK="stocklens-independent-staging"
[[ "$REGION" == eu-central-1 ]] || { echo "REFUSE_NON_STAGING_REGION" >&2; exit 2; }
command -v aws >/dev/null && command -v python3 >/dev/null || {
  echo "AWS_CLI_OR_PYTHON_REQUIRED" >&2; exit 2;
}
STATUS="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query 'Stacks[0].StackStatus' --output text)"
[[ "$STATUS" == CREATE_COMPLETE || "$STATUS" == UPDATE_COMPLETE ]] || {
  echo "NO_COMPLETED_STAGING_STACK:$STATUS" >&2; exit 3;
}
stack_output() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue|[0]" --output text
}
signal_rule="$(stack_output CandidateSignalOnlyRuleName)"
paper_rule="$(stack_output CandidatePaperOnlyRuleName)"
combined_rule="$(stack_output CandidateOrchestratorRuleName)"
bucket="$(stack_output CandidateDataBucket)"
topic="$(stack_output CandidateAlertsTopic)"
[[ -n "$signal_rule" && "$signal_rule" != None &&
   -n "$paper_rule" && "$paper_rule" != None &&
   -n "$combined_rule" && "$combined_rule" != None &&
   -n "$bucket" && "$bucket" != None &&
   -n "$topic" && "$topic" != None ]] || {
  echo "STAGING_RELEASE_OUTPUTS_INCOMPLETE" >&2; exit 3;
}
for rule in "$signal_rule" "$paper_rule" "$combined_rule"; do
  state="$(aws events describe-rule --region "$REGION" --name "$rule" \
    --query State --output text)"
  [[ "$state" == DISABLED ]] || {
    echo "RELEASE_REFUSES_ENABLED_TRADING_SCHEDULE:$rule:$state" >&2; exit 3;
  }
done
watchdog_rule="$(aws cloudformation describe-stack-resource --region "$REGION" \
  --stack-name "$STACK" --logical-resource-id CandidateSessionWatchdogSchedule \
  --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$(aws events describe-rule --region "$REGION" --name "$watchdog_rule" \
  --query State --output text)" == ENABLED ]] || {
  echo "STAGING_WATCHDOG_NOT_ENABLED" >&2; exit 3;
}
[[ "$(aws s3api get-bucket-versioning --region "$REGION" --bucket "$bucket" \
  --query Status --output text)" == Enabled ]] || {
  echo "STAGING_VERSIONING_OFF" >&2; exit 3;
}
public="$(aws s3api get-public-access-block --region "$REGION" --bucket "$bucket" \
  --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' \
  --output text)"
[[ "$public" == $'True\tTrue\tTrue\tTrue' ]] || {
  echo "STAGING_BUCKET_PUBLIC_ACCESS_BLOCK_FAIL" >&2; exit 3;
}
# Verify five function entrypoints; no requirement for reserved concurrency.
for pair in \
  "CandidateFunctionName:infra.aws.independent_pipeline.handler" \
  "CandidatePaperFunctionName:infra.aws.independent_paper.handler" \
  "CandidatePaperPreflightFunctionName:infra.aws.independent_paper.preflight_handler" \
  "CandidateOrchestratorFunctionName:infra.aws.independent_orchestrator.handler" \
  "CandidateSessionWatchdogFunctionName:infra.aws.independent_session_watchdog.handler"
do
  key="${pair%%:*}"; handler="${pair#*:}"
  fn="$(stack_output "$key")"
  [[ -n "$fn" && "$fn" != None ]] || { echo "MISSING_LAMBDA_OUTPUT:$key" >&2; exit 3; }
  actual="$(aws lambda get-function-configuration --region "$REGION" --function-name "$fn" \
    --query '[State,Runtime,Handler]' --output text)"
  [[ "$actual" == $'Active\tpython3.12\t'"$handler" ]] || {
    echo "INVALID_STAGING_LAMBDA_RUNTIME_OR_HANDLER:$key:$actual" >&2; exit 3;
  }
done

# Validate the DEPLOYED preflight role is not accidentally escalated with
# attached or extra inline policies. The allow-list reflects CloudFormation.
preflight_role="$(aws cloudformation describe-stack-resource --region "$REGION" \
  --stack-name "$STACK" --logical-resource-id CandidatePaperPreflightRole \
  --query StackResourceDetail.PhysicalResourceId --output text)"
attached="$(aws iam list-attached-role-policies --role-name "$preflight_role" \
  --query 'length(AttachedPolicies)' --output text)"
[[ "$attached" == 0 ]] || { echo "PREFLIGHT_ROLE_HAS_ATTACHED_POLICY" >&2; exit 3; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
aws iam list-role-policies --role-name "$preflight_role" \
  --query PolicyNames --output json > "$tmp/policies.json"
python3 - "$tmp/policies.json" <<'PY'
import json,sys
with open(sys.argv[1]) as f: names=json.load(f)
if names!=["ReadOnlyStagingPaperPreflight"]:
    raise SystemExit("PREFLIGHT_ROLE_HAS_UNEXPECTED_INLINE_POLICY")
PY
aws iam get-role-policy --role-name "$preflight_role" \
  --policy-name ReadOnlyStagingPaperPreflight --query PolicyDocument \
  --output json > "$tmp/iam.json"
python3 - "$tmp/iam.json" "$bucket" <<'PY'
import json,sys
with open(sys.argv[1]) as f: p=json.load(f)
bucket=sys.argv[2]
allowed={"s3:GetObject","s3:GetObjectVersion","s3:ListBucket",
         "logs:CreateLogStream","logs:PutLogEvents"}
statements=p.get("Statement",[])
actions=set()
for st in statements:
    if st.get("Effect")!="Allow" or "NotAction" in st:
        raise SystemExit("PREFLIGHT_POLICY_UNEXPECTED_STATEMENT")
    aa=st["Action"] if isinstance(st["Action"],list) else [st["Action"]]
    actions.update(aa)
    if any(a.startswith("s3:") for a in aa):
        resources=st["Resource"] if isinstance(st["Resource"],list) else [st["Resource"]]
        if not all(r==f"arn:aws:s3:::{bucket}" or
                   r.startswith(f"arn:aws:s3:::{bucket}/") for r in resources):
            raise SystemExit("PREFLIGHT_S3_SCOPE_ESCALATION")
if actions!=allowed:
    raise SystemExit("PREFLIGHT_POLICY_NOT_READONLY:"+str(actions))
print("READONLY_IAM_GUARD_PASS")
PY
# Verify the deployed alarms actually route to the Staging SNS topic.
for logical in CandidateSignalErrorsAlarm CandidatePaperErrorsAlarm \
  CandidateSessionWatchdogErrorsAlarm MissingOrLateScheduledSignalsAlarm \
  WatchdogHeartbeatDeadmanAlarm WatchdogFailClosedAlarm; do
  physical="$(aws cloudformation describe-stack-resource --region "$REGION" \
    --stack-name "$STACK" --logical-resource-id "$logical" \
    --query StackResourceDetail.PhysicalResourceId --output text)"
  aws cloudwatch describe-alarms --region "$REGION" --alarm-names "$physical" \
    --query 'MetricAlarms[0].{ActionsEnabled:ActionsEnabled,AlarmActions:AlarmActions}' \
    --output json > "$tmp/alarm.json"
  python3 - "$tmp/alarm.json" "$topic" "$logical" <<'PY'
import json,sys
with open(sys.argv[1]) as f: alarm=json.load(f)
if not alarm or alarm.get("ActionsEnabled") is not True or sys.argv[2] not in alarm.get("AlarmActions",[]):
    raise SystemExit("STAGING_ALARM_NOT_WIRED:"+sys.argv[3])
PY
done
account="$(aws sts get-caller-identity --query Account --output text)"
budget="$(aws budgets describe-budget --region us-east-1 --account-id "$account" \
  --budget-name StockLens-Whole-Account-20USD \
  --query 'Budget.BudgetLimit.Amount' --output text)"
python3 - "$budget" <<'PY'
from decimal import Decimal
import sys
if not Decimal(0) < Decimal(sys.argv[1]) <= Decimal(20):
    raise SystemExit("ACCOUNT_COST_BUDGET_ABOVE_20")
PY

confirmed="$(aws sns list-subscriptions-by-topic --region "$REGION" \
  --topic-arn "$topic" \
  --query "Subscriptions[?Protocol=='email' && SubscriptionArn!='PendingConfirmation'].SubscriptionArn" \
  --output text)"
echo "STAGING_RELEASE_INFRA_AUDIT_PASS:five_lambdas:three_trading_rules_disabled:watchdog_enabled:readonly_preflight:alarms_linked:budget_max_20"
if [[ -z "$confirmed" || "$confirmed" == None ]]; then
  echo "EXTERNAL_NO_GO:STAGING_SNS_EMAIL_UNCONFIRMED"
  exit 4
fi
echo "STAGING_SNS_SUBSCRIPTION_CONFIRMED"
echo "EXTERNAL_NO_GO:REAL_EMAIL_ALARM_DELIVERY_NOT_PROVEN_BY_THIS_READ_ONLY_AUDIT"
echo "EXTERNAL_NO_GO:SECOND_PROVIDER_PARITY_AND_PROSPECTIVE_PAPER_NOT_PROVEN"
echo "NO_AUTOMATION_OR_BROKER_ENABLED_BY_RELEASE_AUDIT"
