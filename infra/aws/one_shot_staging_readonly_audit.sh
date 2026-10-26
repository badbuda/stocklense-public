#!/usr/bin/env bash
# Read-only, operator-triggered status audit. Never mutates AWS or invokes Lambda.
set -euo pipefail
export AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1 AWS_PAGER=""
OLD=stocklens-paper
NEW=stocklens-independent-staging
REF=810318f6d316199ef50c4bba3efb96a70646c28d
[[ "$(aws sts get-caller-identity --query Account --output text)" == 634740393398 ]] || { echo "WRONG_AWS_ACCOUNT"; exit 3; }
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
errors=0
block() { echo "BLOCKED:$*"; errors=$((errors+1)); }
output() { aws cloudformation describe-stacks --stack-name "$1" --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue|[0]" --output text; }
physical() { aws cloudformation describe-stack-resource --stack-name "$OLD" --logical-resource-id "$1" --query StackResourceDetail.PhysicalResourceId --output text; }
bucket="$(output "$NEW" CandidateDataBucket)"
[[ -n "$bucket" && "$bucket" != None ]] || { echo "NO_STAGING_BUCKET"; exit 3; }
status="$(aws cloudformation describe-stacks --stack-name "$NEW" --query 'Stacks[0].StackStatus' --output text)"
[[ "$status" == UPDATE_COMPLETE || "$status" == CREATE_COMPLETE ]] || block "STACK_NOT_COMPLETE:$status"
[[ "$(aws s3api get-bucket-versioning --bucket "$bucket" --query Status --output text)" == Enabled ]] || block "S3_VERSIONING_OFF"
public="$(aws s3api get-public-access-block --bucket "$bucket" --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' --output text)"
[[ "$public" == $'True\tTrue\tTrue\tTrue' ]] || block "PUBLIC_ACCESS_NOT_FULLY_BLOCKED"
for pair in CandidateSignalOnlyRuleName:ENABLED CandidatePaperOnlyRuleName:DISABLED CandidateOrchestratorRuleName:DISABLED; do
  key="${pair%%:*}"
  expected="${pair#*:}"
  id="$(output "$NEW" "$key")"
  state="$(aws events describe-rule --name "$id" --query State --output text)"
  echo "STAGING_RULE:$key:$state"
  [[ "$state" == "$expected" ]] || block "STAGING_RULE_STATE:$key"
done
sig="$(output "$NEW" CandidateSignalOnlyRuleName)"
[[ "$(aws events describe-rule --name "$sig" --query ScheduleExpression --output text)" == 'cron(30 2 ? * TUE-SAT *)' ]] || block "STAGING_SIGNAL_CRON"
for name in NightlyRule PaperEvidenceSchedule WatchdogSchedule; do
  state="$(aws events describe-rule --name "$(physical "$name")" --query State --output text)"
  echo "LEGACY_RULE:$name:$state"
  [[ "$state" == DISABLED ]] || block "LEGACY_RULE_REENABLED:$name"
done
for name in ErrorAlarm PaperEvidenceAlarm WatchdogErrorAlarm WatchdogHeartbeatAlarm; do
  state="$(aws cloudwatch describe-alarms --alarm-names "$(physical "$name")" --query 'MetricAlarms[0].ActionsEnabled' --output text)"
  echo "LEGACY_ALARM:$name:actions_enabled=$state"
  [[ "$state" == False ]] || block "LEGACY_ALARM_REENABLED:$name"
done
table="$(output "$OLD" TableName)"
[[ "$(aws dynamodb describe-table --table-name "$table" --query Table.TableStatus --output text)" == ACTIVE ]] || block "HISTORICAL_DYNAMODB_NOT_ACTIVE"
for key in CandidateFunctionName CandidatePaperFunctionName CandidatePaperPreflightFunctionName CandidateOrchestratorFunctionName CandidateSessionWatchdogFunctionName; do
  fn="$(output "$NEW" "$key")"
  if [[ -z "$fn" || "$fn" == None ]]; then
    block "LAMBDA_NOT_DEPLOYED:$key"
  else
    if config="$(aws lambda get-function-configuration --function-name "$fn" --query '[State,LastUpdateStatus,Runtime,Handler]' --output text 2>/dev/null)"; then
      echo "STAGING_LAMBDA:$key:$config"
      [[ "$config" == Active
  fi
done
curl -fsSL --retry 3 "https://raw.githubusercontent.com/badbuda/stocklense-public/$REF/infra/aws/staging_readonly_status.py" -o "$work/status.py"
[[ "$(git hash-object "$work/status.py")" == 2e550e4f032289b21f3a41bff7cb326eb6e0106a ]] || { echo "PINNED_AUDIT_HASH_MISMATCH"; exit 3; }
if python3 "$work/status.py" --session 2026-10-20 --session 2026-10-21 --session 2026-10-22 --session 2026-10-23 > "$work/report.json"; then
  echo "STAGING_SIGNAL_RECEIPT_AUDIT:PASS_S3_ONLY"
else
  block "SIGNAL_RECEIPT_INCOMPLETE_LATE_OR_INVALID"
fi
python3 - "$work/report.json" <<'PY'
import json,sys
o=json.load(open(sys.argv[1]))
print("SIGNAL_STATUS:",o.get("status"))
for r in o.get("receipts",[]):
    print("SIGNAL:",r.get("session"),r.get("status"),"sha256="+str(r.get("sha256","UNVERIFIED"))[:16])
PY
genesis="paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json"
if aws s3api head-object --bucket "$bucket" --key "$genesis" >/dev/null 2>&1; then
  echo "PAPER_GENESIS_PRESENT:ACCOUNTING_NOT_YET_VERIFIED"
else
  block "PAPER_GENESIS_NOT_FOUND_OR_UNREADABLE"
fi
echo "AUDIT_READ_ONLY:NO_LAMBDA_INVOKE:NO_S3_WRITE:NO_ORDER"
echo "NOT_PROVEN:EVENTBRIDGE_PROVENANCE,PROVIDER_PARITY,PAPER_ACCOUNTING,DASHBOARD_LIVE_SOURCE"
if ((errors)); then echo "AUDIT_BLOCKED:$errors"; exit 2; fi
echo "INFRA_S3_RECEIPTS_PASS_ONLY:OTHER_GATES_STILL_REQUIRED"
\t'Successful
  fi
done
curl -fsSL --retry 3 "https://raw.githubusercontent.com/badbuda/stocklense-public/$REF/infra/aws/staging_readonly_status.py" -o "$work/status.py"
[[ "$(git hash-object "$work/status.py")" == 2e550e4f032289b21f3a41bff7cb326eb6e0106a ]] || { echo "PINNED_AUDIT_HASH_MISMATCH"; exit 3; }
if python3 "$work/status.py" --session 2026-10-20 --session 2026-10-21 --session 2026-10-22 --session 2026-10-23 > "$work/report.json"; then
  echo "STAGING_SIGNAL_RECEIPT_AUDIT:PASS_S3_ONLY"
else
  block "SIGNAL_RECEIPT_INCOMPLETE_LATE_OR_INVALID"
fi
python3 - "$work/report.json" <<'PY'
import json,sys
o=json.load(open(sys.argv[1]))
print("SIGNAL_STATUS:",o.get("status"))
for r in o.get("receipts",[]):
    print("SIGNAL:",r.get("session"),r.get("status"),"sha256="+str(r.get("sha256","UNVERIFIED"))[:16])
PY
genesis="paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json"
if aws s3api head-object --bucket "$bucket" --key "$genesis" >/dev/null 2>&1; then
  echo "PAPER_GENESIS_PRESENT:ACCOUNTING_NOT_YET_VERIFIED"
else
  block "PAPER_GENESIS_NOT_FOUND_OR_UNREADABLE"
fi
echo "AUDIT_READ_ONLY:NO_LAMBDA_INVOKE:NO_S3_WRITE:NO_ORDER"
echo "NOT_PROVEN:EVENTBRIDGE_PROVENANCE,PROVIDER_PARITY,PAPER_ACCOUNTING,DASHBOARD_LIVE_SOURCE"
if ((errors)); then echo "AUDIT_BLOCKED:$errors"; exit 2; fi
echo "INFRA_S3_RECEIPTS_PASS_ONLY:OTHER_GATES_STILL_REQUIRED"
\t'python3.12
  fi
done
curl -fsSL --retry 3 "https://raw.githubusercontent.com/badbuda/stocklense-public/$REF/infra/aws/staging_readonly_status.py" -o "$work/status.py"
[[ "$(git hash-object "$work/status.py")" == 2e550e4f032289b21f3a41bff7cb326eb6e0106a ]] || { echo "PINNED_AUDIT_HASH_MISMATCH"; exit 3; }
if python3 "$work/status.py" --session 2026-10-20 --session 2026-10-21 --session 2026-10-22 --session 2026-10-23 > "$work/report.json"; then
  echo "STAGING_SIGNAL_RECEIPT_AUDIT:PASS_S3_ONLY"
else
  block "SIGNAL_RECEIPT_INCOMPLETE_LATE_OR_INVALID"
fi
python3 - "$work/report.json" <<'PY'
import json,sys
o=json.load(open(sys.argv[1]))
print("SIGNAL_STATUS:",o.get("status"))
for r in o.get("receipts",[]):
    print("SIGNAL:",r.get("session"),r.get("status"),"sha256="+str(r.get("sha256","UNVERIFIED"))[:16])
PY
genesis="paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json"
if aws s3api head-object --bucket "$bucket" --key "$genesis" >/dev/null 2>&1; then
  echo "PAPER_GENESIS_PRESENT:ACCOUNTING_NOT_YET_VERIFIED"
else
  block "PAPER_GENESIS_NOT_FOUND_OR_UNREADABLE"
fi
echo "AUDIT_READ_ONLY:NO_LAMBDA_INVOKE:NO_S3_WRITE:NO_ORDER"
echo "NOT_PROVEN:EVENTBRIDGE_PROVENANCE,PROVIDER_PARITY,PAPER_ACCOUNTING,DASHBOARD_LIVE_SOURCE"
if ((errors)); then echo "AUDIT_BLOCKED:$errors"; exit 2; fi
echo "INFRA_S3_RECEIPTS_PASS_ONLY:OTHER_GATES_STILL_REQUIRED"
\t'* ]] || block "LAMBDA_CONFIG:$key"
    else
      block "LAMBDA_UNREADABLE:$key"
    fi
  fi
done
curl -fsSL --retry 3 "https://raw.githubusercontent.com/badbuda/stocklense-public/$REF/infra/aws/staging_readonly_status.py" -o "$work/status.py"
[[ "$(git hash-object "$work/status.py")" == 2e550e4f032289b21f3a41bff7cb326eb6e0106a ]] || { echo "PINNED_AUDIT_HASH_MISMATCH"; exit 3; }
if python3 "$work/status.py" --session 2026-10-20 --session 2026-10-21 --session 2026-10-22 --session 2026-10-23 > "$work/report.json"; then
  echo "STAGING_SIGNAL_RECEIPT_AUDIT:PASS_S3_ONLY"
else
  block "SIGNAL_RECEIPT_INCOMPLETE_LATE_OR_INVALID"
fi
python3 - "$work/report.json" <<'PY'
import json,sys
o=json.load(open(sys.argv[1]))
print("SIGNAL_STATUS:",o.get("status"))
for r in o.get("receipts",[]):
    print("SIGNAL:",r.get("session"),r.get("status"),"sha256="+str(r.get("sha256","UNVERIFIED"))[:16])
PY
genesis="paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json"
if aws s3api head-object --bucket "$bucket" --key "$genesis" >/dev/null 2>&1; then
  echo "PAPER_GENESIS_PRESENT:ACCOUNTING_NOT_YET_VERIFIED"
else
  block "PAPER_GENESIS_NOT_FOUND_OR_UNREADABLE"
fi
echo "AUDIT_READ_ONLY:NO_LAMBDA_INVOKE:NO_S3_WRITE:NO_ORDER"
echo "NOT_PROVEN:EVENTBRIDGE_PROVENANCE,PROVIDER_PARITY,PAPER_ACCOUNTING,DASHBOARD_LIVE_SOURCE"
if ((errors)); then echo "AUDIT_BLOCKED:$errors"; exit 2; fi
echo "INFRA_S3_RECEIPTS_PASS_ONLY:OTHER_GATES_STILL_REQUIRED"
