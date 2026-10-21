#!/usr/bin/env bash
# Reviewed retirement of OLD stocklens-paper EventBridge schedules only.
# Preserves the old DynamoDB table, log groups, IAM and all historical receipts.
set -euo pipefail
export AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1 AWS_PAGER=""
STACK=stocklens-paper

[[ "$#" == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
  echo "USAGE: $0 <PINNED_GREEN_COMMIT_SHA>" >&2; exit 2;
}
[[ "$(git rev-parse HEAD)" == "$1" && -z "$(git status --porcelain)" ]] || {
  echo "REFUSE_UNPINNED_OR_DIRTY_CHECKOUT" >&2; exit 3;
}
[[ "$(aws sts get-caller-identity --query Account --output text)" == 634740393398 ]] || {
  echo "WRONG_AWS_ACCOUNT" >&2; exit 3;
}
[[ "$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text)" == UPDATE_COMPLETE ]] || {
  echo "LEGACY_STACK_NOT_UPDATE_COMPLETE" >&2; exit 3;
}
for logical in NightlyRule PaperEvidenceSchedule WatchdogSchedule; do
  rule="$(aws cloudformation describe-stack-resource --stack-name "$STACK" --logical-resource-id "$logical" --query StackResourceDetail.PhysicalResourceId --output text)"
  [[ -n "$rule" && "$rule" != None ]] || { echo "LEGACY_RULE_NOT_FOUND:$logical" >&2; exit 3; }
  [[ "$(aws events describe-rule --name "$rule" --query State --output text)" == ENABLED ]] || {
    echo "LEGACY_RULE_NOT_ENABLED:$logical" >&2; exit 3;
  }
done

# Replacement Staging keeps its independently observed Signal producer enabled.
[[ "$(aws cloudformation describe-stacks --stack-name stocklens-independent-staging --query 'Stacks[0].StackStatus' --output text)" == UPDATE_COMPLETE ]] || {
  echo "INDEPENDENT_STAGING_NOT_READY" >&2; exit 3;
}
signal_rule="$(aws cloudformation describe-stacks --stack-name stocklens-independent-staging --query "Stacks[0].Outputs[?OutputKey=='CandidateSignalOnlyRuleName'].OutputValue|[0]" --output text)"
[[ "$(aws events describe-rule --name "$signal_rule" --query State --output text)" == ENABLED ]] || {
  echo "INDEPENDENT_SIGNAL_NOT_ENABLED" >&2; exit 3;
}
bucket="$(aws cloudformation describe-stacks --stack-name stocklens-independent-staging --query "Stacks[0].Outputs[?OutputKey=='CandidateDataBucket'].OutputValue|[0]" --output text)"
version="$(aws s3api head-object --bucket "$bucket" --key signals/2026-10-20.json --query VersionId --output text)"
[[ -n "$version" && "$version" != None && "$version" != null ]] || {
  echo "REPLACEMENT_SIGNAL_RECEIPT_MISSING" >&2; exit 3;
}
table="$(aws cloudformation describe-stack-resource --stack-name "$STACK" --logical-resource-id Signals --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$(aws dynamodb describe-table --table-name "$table" --query Table.TableStatus --output text)" == ACTIVE ]] || {
  echo "LEGACY_DYNAMODB_NOT_ACTIVE" >&2; exit 3;
}
grep -q 'DeletionPolicy: Retain' infra/aws/paper-signal-journal.yaml || {
  echo "DYNAMODB_RETAIN_POLICY_MISSING" >&2; exit 3;
}
aws cloudformation validate-template --template-body file://infra/aws/paper-signal-journal.yaml >/dev/null

# Stage a CloudFormation changeset for review BEFORE any stack change.
name="stocklens-retire-legacy-$(date -u +%Y%m%d%H%M%S)"
aws cloudformation create-change-set --stack-name "$STACK" --change-set-name "$name" \
  --change-set-type UPDATE --template-body file://infra/aws/paper-signal-journal.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=LegacyArchiveState,ParameterValue=DISABLED \
               ParameterKey=AlertEmail,UsePreviousValue=true >/dev/null
echo "CHANGE_SET_CREATED:$name"
if ! aws cloudformation wait change-set-create-complete --stack-name "$STACK" --change-set-name "$name"; then
  echo "CHANGE_SET_FAILED_OR_EMPTY_INSPECT_ONLY:$name" >&2; exit 4;
fi
changes="$(aws cloudformation describe-change-set --stack-name "$STACK" --change-set-name "$name" --query Changes --output json)"
python3 - "$changes" <<'PY'
import json,sys
changes=json.loads(sys.argv[1])
allowed={"NightlyRule","PaperEvidenceSchedule","WatchdogSchedule"}
found=set()
for change in changes:
    item=change.get("ResourceChange",{})
    name=item.get("LogicalResourceId")
    if name not in allowed or item.get("Action")!="Modify" or item.get("Replacement") not in ("False",False):
        raise SystemExit("UNEXPECTED_CHANGESET_RESOURCE:"+str((name,item.get("Action"),item.get("Replacement"))))
    found.add(name)
if found!=allowed:
    raise SystemExit("EXPECTED_THREE_RULE_MODIFICATIONS:"+str(sorted(found)))
print("CHANGES_ONLY_THREE_EVENTBRIDGE_RULES:NO_DYNAMODB_OR_ALARM_CHANGES")
PY
echo "REVIEW_ONLY_COMPLETED_CHANGESET:$name"
read -r -p 'Type EXECUTE_LEGACY_RETIREMENT to disable old archive + watchdog schedules: ' answer
[[ "$answer" == EXECUTE_LEGACY_RETIREMENT ]] || {
  echo "CANCELLED_NO_STACK_UPDATE:CHANGES_SET_REMAINS_FOR_REVIEW:$name"; exit 3;
}
aws cloudformation execute-change-set --stack-name "$STACK" --change-set-name "$name"
aws cloudformation wait stack-update-complete --stack-name "$STACK" || {
  echo "RETIREMENT_UPDATE_FAILED_INSPECT_STACK_EVENTS_AND_ROLLBACK" >&2; exit 5;
}
for logical in NightlyRule PaperEvidenceSchedule WatchdogSchedule; do
  rule="$(aws cloudformation describe-stack-resource --stack-name "$STACK" --logical-resource-id "$logical" --query StackResourceDetail.PhysicalResourceId --output text)"
  [[ "$(aws events describe-rule --name "$rule" --query State --output text)" == DISABLED ]] || {
    echo "RETIREMENT_RULE_NOT_DISABLED:$logical" >&2; exit 6;
  }
  echo "LEGACY_RULE_RETIRED:$logical"
done
[[ "$(aws dynamodb describe-table --table-name "$table" --query Table.TableStatus --output text)" == ACTIVE ]] || {
  echo "LEGACY_DYNAMODB_STATE_NOT_ACTIVE" >&2; exit 6;
}
echo "LEGACY_ARCHIVE_SCHEDULES_RETIRED_HISTORY_RETAINED"
echo "STAGING_SIGNAL_ACTIVE_AND_PAPER_DISABLED_NO_BROKER"
echo "Old CloudWatch alarms are intentionally preserved; past alarms may remain ALARM until their 5-min metric ages out."
