#!/usr/bin/env bash
# CloudFormation-only coordinated retirement of the OBSOLETE stocklens-paper stack.
# No deletion, no write to DynamoDB, no changes to stocklens-independent-staging.
# PREVIEW/STATUS are read-only except that PLAN creates an inert CloudFormation
# change set. RETIRE always requires an explicit operator-typed approval.
set -euo pipefail
export AWS_PAGER=""
REGION="eu-central-1"
ACCOUNT="634740393398"
LEGACY="stocklens-paper"
STAGING="stocklens-independent-staging"
MODE="${1:-status}"
[[ "${AWS_REGION:-$REGION}" == "$REGION" && "${AWS_DEFAULT_REGION:-$REGION}" == "$REGION" ]] || {
  echo "REFUSE_NON_STAGING_REGION" >&2; exit 3;
}
[[ "$MODE" == status || "$MODE" == retire ]] || {
  echo "Usage: bash infra/aws/retire_legacy_stocklens.sh status|retire" >&2; exit 3;
}
for bin in aws python3; do command -v "$bin" >/dev/null || { echo "MISSING:$bin" >&2; exit 3; }; done
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || {
  echo "WRONG_AWS_ACCOUNT" >&2; exit 3;
}
stack_status="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$LEGACY" --query 'Stacks[0].StackStatus' --output text)"
[[ "$stack_status" == CREATE_COMPLETE || "$stack_status" == UPDATE_COMPLETE ]] || {
  echo "LEGACY_STACK_NOT_READY:$stack_status" >&2; exit 3;
}
legacy_param="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$LEGACY" --query "Stacks[0].Parameters[?ParameterKey=='LegacyRetirementMode'].ParameterValue|[0]" --output text)"
table="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$LEGACY" --query "Stacks[0].Outputs[?OutputKey=='TableName'].OutputValue|[0]" --output text)"
[[ -n "$table" && "$table" != None ]] || { echo "LEGACY_TABLE_ID_MISSING" >&2; exit 3; }
[[ "$(aws dynamodb describe-table --region "$REGION" --table-name "$table" --query Table.TableStatus --output text)" == ACTIVE ]] || {
  echo "LEGACY_TABLE_NOT_ACTIVE" >&2; exit 3;
}
resource_id() {
  aws cloudformation describe-stack-resource --region "$REGION" --stack-name "$LEGACY" \
    --logical-resource-id "$1" --query StackResourceDetail.PhysicalResourceId --output text
}
rule_state() { aws events describe-rule --region "$REGION" --name "$1" --query State --output text; }
for logical in NightlyRule PaperEvidenceSchedule WatchdogSchedule; do
  actual="$(resource_id "$logical")"
  [[ -n "$actual" && "$actual" != None ]] || { echo "MISSING_RULE:$logical" >&2; exit 3; }
  state="$(rule_state "$actual")"
  echo "LEGACY_RULE:$logical:$state"
  if [[ "$MODE" == retire && "$state" != ENABLED ]]; then
    echo "REFUSE_PARTIALLY_RETIRED_RULE:$logical:$state" >&2; exit 3;
  fi
done
for logical in ErrorAlarm PaperEvidenceAlarm WatchdogErrorAlarm WatchdogHeartbeatAlarm; do
  actual="$(resource_id "$logical")"
  actions="$(aws cloudwatch describe-alarms --region "$REGION" --alarm-names "$actual" --query 'MetricAlarms[0].AlarmActions' --output json)"
  echo "LEGACY_ALARM:$logical:actions_present=$(python3 -c 'import json,sys;print(bool(json.loads(sys.argv[1])))' "$actions")"
  if [[ "$MODE" == retire ]]; then
    python3 - "$actions" "$logical" <<'PY'
import json,sys
if not json.loads(sys.argv[1]):
    raise SystemExit("REFUSE_PARTIALLY_RETIRED_ALARM:"+sys.argv[2])
PY
  fi
done
signal_rule="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STAGING" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidateSignalOnlyRuleName'].OutputValue|[0]" --output text)"
[[ -n "$signal_rule" && "$signal_rule" != None ]] || { echo "STAGING_SIGNAL_RULE_UNKNOWN" >&2; exit 3; }
new_state="$(rule_state "$signal_rule")"
new_schedule="$(aws events describe-rule --region "$REGION" --name "$signal_rule" --query ScheduleExpression --output text)"
[[ "$new_state" == ENABLED && "$new_schedule" == 'cron(30 2 ? * TUE-SAT *)' ]] || {
  echo "STAGING_SIGNAL_NOT_ACTIVE_OR_WRONG_SCHEDULE" >&2; exit 3;
}
echo "STAGING_SIGNAL:ENABLED:02:30UTC"
echo "LEGACY_DYNAMODB:ACTIVE:preserved_table=$table"
echo "LEGACY_RETIREMENT_PARAMETER:$legacy_param"
if [[ "$MODE" == status ]]; then
  echo "READ_ONLY_LEGACY_STATUS_COMPLETE:NO_AWS_MUTATIONS"
  exit 0
fi
[[ "$legacy_param" == None || "$legacy_param" == RUNNING ]] || {
  echo "LEGACY_ALREADY_RETIRED_OR_UNEXPECTED_STATE:$legacy_param" >&2; exit 3;
}
[[ -f infra/aws/paper-signal-journal.yaml && -f ci_transfer_manifest.json ]] || {
  echo "REQUIRE_REPO_ROOT" >&2; exit 3;
}
[[ "${EXPECTED_LEGACY_RETIRE_COMMIT:-}" =~ ^[a-f0-9]{40}$ ]] || {
  echo "REQUIRE_GREEN_REVIEWED_LEGACY_RETIRE_SHA" >&2; exit 3;
}
[[ "$(git rev-parse HEAD)" == "$EXPECTED_LEGACY_RETIRE_COMMIT" ]] || {
  echo "REFUSE_NONPINNED_GIT_HEAD" >&2; exit 3;
}
[[ -z "$(git status --porcelain)" ]] || { echo "REFUSE_DIRTY_GIT_TREE" >&2; exit 3; }
python3 ci_transfer_guard.py >/dev/null
aws cloudformation validate-template --region "$REGION" \
  --template-body file://infra/aws/paper-signal-journal.yaml >/dev/null
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
change_set="stocklens-retire-legacy-$(date -u +%Y%m%d%H%M%S)"
echo "CREATING_INERT_CHANGESET:$change_set (NO RESOURCES ALTERED YET)"
aws cloudformation create-change-set --region "$REGION" --stack-name "$LEGACY" \
  --change-set-name "$change_set" --change-set-type UPDATE \
  --template-body file://infra/aws/paper-signal-journal.yaml \
  --parameters ParameterKey=AlertEmail,UsePreviousValue=true \
               ParameterKey=LegacyRetirementMode,ParameterValue=RETIRED \
  --capabilities CAPABILITY_IAM >/dev/null
aws cloudformation wait change-set-create-complete --region "$REGION" \
  --stack-name "$LEGACY" --change-set-name "$change_set" || {
    echo "CHANGESET_NOT_READY:NO_STACK_MUTATION:inspect=$change_set" >&2; exit 4;
  }
aws cloudformation describe-change-set --region "$REGION" \
  --stack-name "$LEGACY" --change-set-name "$change_set" \
  --output json >"$tmp/change-set.json"
python3 infra/aws/verify_legacy_retirement_changeset.py "$tmp/change-set.json"
echo "ALLOWED_ONLY:three EventBridge DISABLED, four legacy alarm notifications removed."
echo "NO_DELETE:NO_TABLE_CHANGE:NO_IAM_CHANGE:NO_STAGING_CHANGE."
read -r -p "Type RETIRE_OLD_STOCKLENS_PAPER_SCHEDULES to execute CloudFormation change set: " answer
[[ "$answer" == RETIRE_OLD_STOCKLENS_PAPER_SCHEDULES ]] || {
  echo "NO_CHANGESET_EXECUTION:review_or_delete_inert_changeset=$change_set" >&2; exit 3;
}
aws cloudformation execute-change-set --region "$REGION" \
  --stack-name "$LEGACY" --change-set-name "$change_set"
aws cloudformation wait stack-update-complete --region "$REGION" --stack-name "$LEGACY" || {
  echo "LEGACY_RETIREMENT_UPDATE_NOT_PROVEN:check_cloudformation_stack_events" >&2; exit 4;
}
for logical in NightlyRule PaperEvidenceSchedule WatchdogSchedule; do
  [[ "$(rule_state "$(resource_id "$logical")")" == DISABLED ]] || {
    echo "LEGACY_RULE_NOT_DISABLED:$logical" >&2; exit 4;
  }
done
for logical in ErrorAlarm PaperEvidenceAlarm WatchdogErrorAlarm WatchdogHeartbeatAlarm; do
  alarm="$(resource_id "$logical")"
  [[ "$(aws cloudwatch describe-alarms --region "$REGION" --alarm-names "$alarm" \
       --query 'length(MetricAlarms[0].AlarmActions)' --output text)" == 0 ]] || {
    echo "LEGACY_ALARM_STILL_HAS_NOTIFICATION:$logical" >&2; exit 4;
  }
done
heartbeat="$(resource_id WatchdogHeartbeatAlarm)"
[[ "$(aws cloudwatch describe-alarms --region "$REGION" --alarm-names "$heartbeat" \
    --query 'MetricAlarms[0].TreatMissingData' --output text)" == notBreaching ]] || {
  echo "LEGACY_HEARTBEAT_NOT_RETIRED" >&2; exit 4;
}
[[ "$(rule_state "$signal_rule")" == ENABLED ]] || { echo "NEW_STAGING_SIGNAL_NOT_ENABLED" >&2; exit 4; }
[[ "$(aws dynamodb describe-table --region "$REGION" --table-name "$table" --query Table.TableStatus --output text)" == ACTIVE ]] || {
  echo "LEGACY_ARCHIVED_TABLE_NOT_ACTIVE" >&2; exit 4;
}
echo "LEGACY_RETIREMENT_VERIFIED:three_schedules_disabled:four_alarm_notifications_retired:ddb_retained:staging_signal_enabled"
echo "HISTORY:pre-retirement failures still valid. NEW PAPER REMAINS DISABLED; NO BROKER ACTIONS."
