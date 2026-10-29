#!/usr/bin/env bash
# StockLens ST-only SNS setup and real CloudWatch alarm email test.
# No EventBridge updates, Lambda invocations, S3 writes, PROD or broker calls.
set -euo pipefail
export AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1 AWS_PAGER=""
ACCOUNT=634740393398
STACK=stocklens-st
SOURCE=stocklens-independent-staging
MODE="${1:-}"
[[ "$MODE" == subscribe || "$MODE" == test ]] || { echo "USE: subscribe [--email ADDRESS] | test"; exit 2; }
if [[ "$MODE" == subscribe ]]; then
  [[ "$#" == 1 || ( "$#" == 3 && "$2" == --email && -n "$3" ) ]] || { echo BAD_ARGUMENTS; exit 2; }
else
  [[ "$#" == 1 ]] || { echo BAD_ARGUMENTS;exit 2; }
fi
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || { echo WRONG_ACCOUNT; exit 3; }
STATUS="$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text)"
[[ "$STATUS" == CREATE_COMPLETE || "$STATUS" == UPDATE_COMPLETE ]] || { echo ST_STACK_UNHEALTHY; exit 3; }
out() { aws cloudformation describe-stacks --stack-name "$1" --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue|[0]" --output text; }
TOPIC="$(out "$STACK" CandidateAlertsTopic)"
EXPECTED="arn:aws:sns:eu-central-1:${ACCOUNT}:stocklens-st-candidate-alerts"
[[ "$TOPIC" == "$EXPECTED" ]] || { echo WRONG_ST_SNS_TOPIC; exit 3; }
confirmed() {
  aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" --output json |
    python3 -c 'import json,sys
d=json.load(sys.stdin)
print("\n".join(s["Endpoint"] for s in d.get("Subscriptions",[])
    if s.get("Protocol")=="email" and s.get("SubscriptionArn") not in (None,"PendingConfirmation")))'
}
if [[ "$MODE" == subscribe ]]; then
  if [[ "$#" == 3 ]]; then
    EMAIL="$3"
  else
    SOURCE_TOPIC="$(out "$SOURCE" CandidateAlertsTopic 2>/dev/null || true)"
    CANDIDATES=()
    if [[ "$SOURCE_TOPIC" == arn:aws:sns:eu-central-1:${ACCOUNT}:* ]]; then
      mapfile -t CANDIDATES < <(aws sns list-subscriptions-by-topic \
        --topic-arn "$SOURCE_TOPIC" --output json | python3 -c 'import json,sys
d=json.load(sys.stdin)
print("\n".join(s["Endpoint"] for s in d.get("Subscriptions",[])
    if s.get("Protocol")=="email" and s.get("SubscriptionArn") not in (None,"PendingConfirmation")))')
    fi
    if [[ "${#CANDIDATES[@]}" -eq 1 ]]; then
      EMAIL="${CANDIDATES[0]}"
      echo REUSE_SINGLE_CONFIRMED_STAGING_EMAIL
    else
      read -r -p 'Enter email for ST alerts: ' EMAIL
    fi
  fi
  [[ "$EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || { echo BAD_EMAIL;exit 2; }
  if printf '%s\n' "$(confirmed)" | grep -Fxq -- "$EMAIL"; then
    echo ST_SNS_EMAIL_ALREADY_CONFIRMED
    exit 0
  fi
  aws sns subscribe --topic-arn "$TOPIC" --protocol email \
    --notification-endpoint "$EMAIL" >/dev/null
  echo ST_SNS_CONFIRMATION_REQUESTED
  echo 'Confirm the AWS SNS email, then run: bash "$HOME/stocklens-st-sns.sh" test'
  exit 0
fi
[[ -n "$(confirmed)" ]] || { echo ST_SNS_UNCONFIRMED_CONFIRM_EMAIL_FIRST;exit 4; }
ALARM="$(aws cloudformation describe-stack-resource --stack-name "$STACK" \
  --logical-resource-id CandidateSignalErrorsAlarm \
  --query StackResourceDetail.PhysicalResourceId --output text)"
[[ -n "$ALARM" && "$ALARM" != None ]] || { echo ST_TEST_ALARM_NOT_FOUND;exit 4; }
aws cloudwatch describe-alarms --alarm-names "$ALARM" --output json |
  python3 -c 'import json,sys
a=json.load(sys.stdin).get("MetricAlarms",[])
if len(a)!=1 or a[0].get("AlarmName")!=sys.argv[1]:
    raise SystemExit("ST_ALARM_NOT_FOUND")
m=a[0]
if m.get("AlarmActions")!=[sys.argv[2]] or m.get("ActionsEnabled") is not True:
    raise SystemExit("ST_ALARM_ACTIONS_NOT_CONFIGURED")
if m.get("StateValue")=="ALARM":
    raise SystemExit("ST_ALARM_ALREADY_ACTIVE_REFUSE_OVERRIDE")
print("ST_CLOUDWATCH_TO_SNS_ACTIONS_VERIFIED")' "$ALARM" "$TOPIC"
echo 'TRIGGERING_TEST_ALARM_ON_ST_ONLY:NO_LAMBDA_INVOKE'
aws cloudwatch set-alarm-state --alarm-name "$ALARM" \
  --state-value ALARM --state-reason 'ST_EMAIL_DELIVERY_TEST_ONLY_NO_REAL_SIGNAL_ERROR'
echo ST_CLOUDWATCH_ALARM_TEST_TRIGGERED
echo 'Verify that a CloudWatch ALARM email reaches your inbox before activating Signal.'
