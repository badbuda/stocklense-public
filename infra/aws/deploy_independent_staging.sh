#!/usr/bin/env bash
# Explicit, isolated AWS STAGING deployment; never updates stocklens-paper.
# Run only after reviewing the change set and accepting AWS resource costs.
set -euo pipefail

REGION="${AWS_REGION:-eu-central-1}"
STACK="stocklens-independent-staging"
export AWS_PAGER=""
export AWS_DEFAULT_REGION="$REGION"

if [[ "$REGION" != "eu-central-1" ]]; then
  echo "Refusing deployment outside validated Frankfurt region" >&2; exit 2
fi
for tool in aws python3 git sha256sum; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 2; }
done
if [[ ! -f infra/aws/independent-staging.yaml || ! -f stocklens/core.py ]]; then
  echo "Run from the root of the checked-out StockLens repository" >&2; exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Uncommitted or untracked repository changes: refusing non-reproducible package" >&2; exit 2
fi

# Diagnose CloudFormation failures without guessing or deleting resources.
# The account owner must decide whether to clean up a rolled-back stack.
show_staging_events() {
  echo "=== CloudFormation failing events (read-only) ===" >&2
  aws cloudformation describe-stack-events --region "$REGION" \
    --stack-name "$STACK" \
    --query "StackEvents[?contains(ResourceStatus, 'FAILED')].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]" \
    --output table >&2 || true
  echo "=== CloudFormation stack status (read-only) ===" >&2
  aws cloudformation describe-stacks --region "$REGION" \
    --stack-name "$STACK" \
    --query 'Stacks[0].[StackName,StackStatus,StackStatusReason]' \
    --output table >&2 || true
}

EXISTING_STATUS="$(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK" --query 'Stacks[0].StackStatus' \
  --output text 2>/dev/null || true)"
case "$EXISTING_STATUS" in
  ROLLBACK_COMPLETE)
    echo "A previous CREATE rolled back. The stack cannot be updated in place." >&2
    if [[ "${STOCKLENS_RECREATE_ROLLED_BACK_STAGING:-0}" != "1" ]]; then
      show_staging_events
      echo "To RECREATE ONLY this isolated FAILED staging stack, explicitly set" >&2
      echo "STOCKLENS_RECREATE_ROLLED_BACK_STAGING=1 when running this script." >&2
      exit 3
    fi
    # Destruction is opt-in and targets only our exact failed candidate stack.
    # Guard both AWS identity and the original immutable template description.
    ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
    CURRENT_DESCRIPTION="$(aws cloudformation describe-stacks --region "$REGION" \
      --stack-name "$STACK" --query 'Stacks[0].Description' --output text)"
    CURRENT_STACK_ID="$(aws cloudformation describe-stacks --region "$REGION" \
      --stack-name "$STACK" --query 'Stacks[0].StackId' --output text)"
    EXPECTED_DESCRIPTION="StockLens 8.0 AWS-only candidate; isolated, manual-invoke, shadow-only; never replaces stocklens-paper"
    EXPECTED_STACK_PREFIX="arn:aws:cloudformation:${REGION}:${ACCOUNT_ID}:stack/${STACK}/"
    if [[ "$CURRENT_DESCRIPTION" != "$EXPECTED_DESCRIPTION" \
       || "$CURRENT_STACK_ID" != "$EXPECTED_STACK_PREFIX"* \
       || ! "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]]; then
      show_staging_events
      echo "REFUSING DELETION: failed stack identity/description do not match." >&2
      exit 3
    fi
    echo "Explicitly authorized cleanup of ROLLBACK_COMPLETE isolated stack: $STACK" >&2
    echo "Retained CandidateData S3 buckets are NOT deleted by CloudFormation." >&2
    aws cloudformation delete-stack --region "$REGION" --stack-name "$STACK"
    if ! aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$STACK"; then
      show_staging_events
      echo "FAILED TO DELETE: no new deployment attempted." >&2
      exit 3
    fi
    echo "Old failed staging stack deleted. Proceeding with clean staging create." >&2
    ;;
  ""|None|CREATE_COMPLETE|UPDATE_COMPLETE|UPDATE_ROLLBACK_COMPLETE)
    ;;
  *)
    echo "BLOCKED: staging stack status $EXISTING_STATUS; no unsafe overwrite or delete." >&2
    show_staging_events
    exit 3
    ;;
esac
# Migration is a separate explicit one-shot operator path. Default deployment
# remains strictly disarmed and refuses ALL existing active schedules.
ACTIVE_MIGRATION="${STOCKLENS_ACTIVE_SIGNAL_MIGRATION:-0}"
[[ "$ACTIVE_MIGRATION" == 0 || "$ACTIVE_MIGRATION" == 1 ]] || {
  echo "INVALID_SIGNAL_MIGRATION_OPT_IN" >&2; exit 3;
}
SIGNAL_RULE_CF_STATE=DISABLED
if [[ "$ACTIVE_MIGRATION" == 1 ]]; then
  [[ "$EXISTING_STATUS" == UPDATE_COMPLETE || "$EXISTING_STATUS" == CREATE_COMPLETE ]] || {
    echo "MIGRATION_REQUIRES_EXISTING_HEALTHY_STACK" >&2; exit 3;
  }
  account="$(aws sts get-caller-identity --query Account --output text)"
  [[ "$account" == 634740393398 ]] || {
    echo "MIGRATION_WRONG_AWS_ACCOUNT" >&2; exit 3;
  }
  description="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query 'Stacks[0].Description' --output text)"
  [[ "$description" == "StockLens 8.0 AWS-only candidate; isolated, manual-invoke, shadow-only; never replaces stocklens-paper" ]] || {
    echo "MIGRATION_WRONG_STACK_IDENTITY" >&2; exit 3;
  }
  SIGNAL_RULE_CF_STATE=ENABLED
fi
# Never silently turn OFF an opted-in nightly producer with CF's safe
# DISABLED default, nor reset an already anchored monitoring epoch. This guard
# performs only read-only AWS queries before packaging or ANY AWS mutation.
if [[ "$EXISTING_STATUS" == CREATE_COMPLETE || "$EXISTING_STATUS" == UPDATE_COMPLETE ]]; then
  STACK_OUTPUTS="$(aws cloudformation describe-stacks --region "$REGION" \
    --stack-name "$STACK" --query 'Stacks[0].Outputs' --output json)"
  python3 - "$STACK_OUTPUTS" <<'PY'
import json,sys
if not isinstance(json.loads(sys.argv[1]),list):
    raise SystemExit("INVALID_STAGING_OUTPUTS")
PY
  for output_key in CandidateSignalOnlyRuleName CandidatePaperOnlyRuleName CandidateOrchestratorRuleName; do
    old_rule="$(aws cloudformation describe-stacks --region "$REGION" \
      --stack-name "$STACK" \
      --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue|[0]" \
      --output text)"
    if [[ -n "$old_rule" && "$old_rule" != None ]]; then
      rule_state="$(aws events describe-rule --region "$REGION" \
        --name "$old_rule" --query State --output text)"
      if [[ "$ACTIVE_MIGRATION" == 1 && "$output_key" == CandidateSignalOnlyRuleName ]]; then
        [[ "$rule_state" == ENABLED ]] || {
          echo "MIGRATION_SIGNAL_RULE_NOT_ENABLED:$rule_state" >&2; exit 3;
        }
        old_schedule="$(aws events describe-rule --region "$REGION" --name "$old_rule" --query ScheduleExpression --output text)"
        [[ "$old_schedule" == 'cron(10 0 ? * TUE-SAT *)' ]] || {
          echo "MIGRATION_UNEXPECTED_OLD_SIGNAL_SCHEDULE:$old_schedule" >&2; exit 3;
        }
      else
        [[ "$rule_state" == DISABLED ]] || {
          echo "REFUSE_REDEPLOY_ACTIVE_SCHEDULE:$output_key:$rule_state" >&2
          exit 3
        }
      fi
    fi
  done
  data_bucket="$(aws cloudformation describe-stacks --region "$REGION" \
    --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='CandidateDataBucket'].OutputValue|[0]" \
    --output text)"
  if [[ -n "$data_bucket" && "$data_bucket" != None ]]; then
    count="$(aws s3api list-objects-v2 --region "$REGION" --bucket "$data_bucket" \
      --prefix 'monitoring/signal-only-activation.json' --max-keys 1 \
      --query 'KeyCount' --output text)"
    if [[ "$ACTIVE_MIGRATION" == 1 ]]; then
      [[ "$count" == 1 ]] || { echo "MIGRATION_MISSING_SIGNAL_MONITOR_ANCHOR" >&2; exit 3; }
      anchor_version="$(aws s3api head-object --region "$REGION" --bucket "$data_bucket" --key monitoring/signal-only-activation.json --query VersionId --output text)"
      [[ "$anchor_version" != None && -n "$anchor_version" && "$anchor_version" != null ]] || {
        echo "MIGRATION_UNVERSIONED_SIGNAL_ANCHOR" >&2; exit 3;
      }
      # Cannot migrate an already bootstrapped/active Paper book as a Signal-only recovery.
      book_count="$(aws s3api list-objects-v2 --region "$REGION" --bucket "$data_bucket" --prefix 'paper/book/' --max-keys 1 --query KeyCount --output text)"
      [[ "$book_count" == 0 ]] || { echo "MIGRATION_PAPER_BOOK_EXISTS_NEEDS_SEPARATE_PROCEDURE" >&2; exit 3; }
    else
      [[ "$count" == 0 ]] || {
        echo "REFUSE_REDEPLOY_ESTABLISHED_SIGNAL_MONITOR_ANCHOR:count=$count" >&2
        exit 3
      }
    fi
  fi
fi

COMMIT="$(git rev-parse HEAD)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
# Paper uses exact frozen yfinance, pandas and exchange_calendars code paths.
# Native wheels MUST target the same CPython version as the Lambda runtime.
# CloudShell often has Python 3.9/3.11 but no local Python 3.12.
# pip resolves the target *CPython 3.12 / Linux x86_64* wheel tags
# without requiring a CPython 3.12 executable on the build host.
PYTHON_BUILD="${PYTHON_BUILD:-python3}"
"$PYTHON_BUILD" - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("Packaging host needs Python 3.9+ (NOT Python 3.12)")
PY
"$PYTHON_BUILD" -m pip --version >/dev/null || {
  echo "pip unavailable for the host Python; install it before staging" >&2; exit 2;
}
"$PYTHON_BUILD" -m pip install --disable-pip-version-check --no-cache-dir \
  --only-binary=:all: --no-compile \
  --platform manylinux_2_34_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --platform manylinux2014_x86_64 \
  --python-version 3.12 --implementation cp --abi cp312 \
  --target "$TEMP_DIR/deps" -r requirements.txt

"$PYTHON_BUILD" - "$TEMP_DIR/candidate.zip" "$TEMP_DIR/deps" <<'PY'
import sys, zipfile
from pathlib import Path

paths = [
    "infra/aws/independent_market_ingest.py",
    "infra/aws/independent_frozen_ingest.py",
    "infra/aws/independent_pipeline.py",
    "infra/aws/source_parity.py",
    "infra/aws/independent_orchestrator.py",
    "infra/aws/independent_signal_producer.py",
    "infra/aws/independent_paper.py",
    "infra/aws/session_continuity.py",
    "infra/aws/independent_session_watchdog.py",
    "infra/aws/independent_signal_monitor.py",
    "stocklens/core.py",
    "stocklens/data.py",
    "stocklens/paper.py",
    "stocklens/__init__.py",
    "paper_rebalance_math.py",
    "paper_portfolio_integrity.py",
]
deps = Path(sys.argv[2])
if not (deps / "numpy").is_dir() or not (deps / "pandas").is_dir() or not (deps / "yfinance").is_dir():
    raise RuntimeError("MISSING_REQUIRED_LAMBDA_DEPENDENCIES")
# Disallow incompatible native extensions compiled for the CloudShell host.
bad_extensions = []
for path in deps.rglob("*.so"):
    n = path.name
    if ".cpython-" in n and ".cpython-312-" not in n:
        bad_extensions.append(path.as_posix())
if bad_extensions:
    raise RuntimeError("NON_CP312_NATIVE_WHEELS:" + str(bad_extensions[:6]))
files = [(Path(file), file) for file in paths]
for file, _ in files:
    if not file.is_file():
        raise RuntimeError(f"MISSING_PACKAGE_FILE:{file}")
for path in sorted(deps.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
        files.append((path, path.relative_to(deps).as_posix()))
size = sum(path.stat().st_size for path, _ in files)
if size > 240 * 1024 * 1024:
    raise RuntimeError(f"UNZIPPED_LAMBDA_PACKAGE_TOO_LARGE:{size}")
with zipfile.ZipFile(sys.argv[1], "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as out:
    out.writestr("infra/__init__.py", "")
    out.writestr("infra/aws/__init__.py", "")
    names = set()
    for file, dest in files:
        if dest in names:
            raise RuntimeError(f"DUPLICATE_PACKAGE_PATH:{dest}")
        names.add(dest)
        out.write(file, dest)
print(f"Package contents: {len(files)} files, {size} uncompressed bytes")
PY
# Validate deployment inputs BEFORE any AWS resource is created.
aws cloudformation validate-template \
  --template-body file://infra/aws/independent-staging.yaml >/dev/null

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
if [[ ! "$ACCOUNT" =~ ^[0-9]{12}$ ]]; then
  echo "Unexpected AWS account identity" >&2; exit 2
fi
ARTIFACT_BUCKET="stocklens-candidate-artifacts-${ACCOUNT}-${REGION}"
if ! aws s3api head-bucket --bucket "$ARTIFACT_BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$ARTIFACT_BUCKET" \
    --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
fi
aws s3api put-public-access-block --bucket "$ARTIFACT_BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
aws s3api put-bucket-encryption --bucket "$ARTIFACT_BUCKET" \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-versioning --bucket "$ARTIFACT_BUCKET" \
  --versioning-configuration Status=Enabled

DIGEST="$(sha256sum "$TEMP_DIR/candidate.zip" | cut -d' ' -f1)"
ARTIFACT_KEY="candidate/${COMMIT}/${DIGEST}.zip"
if ! aws s3api head-object --bucket "$ARTIFACT_BUCKET" \
  --key "$ARTIFACT_KEY" >/dev/null 2>&1; then
  aws s3api put-object --bucket "$ARTIFACT_BUCKET" \
    --key "$ARTIFACT_KEY" --body "$TEMP_DIR/candidate.zip" \
    --if-none-match '*' --server-side-encryption AES256 >/dev/null
fi
echo "STAGING ONLY: ${STACK}; source commit ${COMMIT}; ZIP sha256 ${DIGEST}"
echo "This deploys FIVE isolated staging Lambdas (including a read-only Paper"
echo "preflight), a private versioned bucket, with Signal state $SIGNAL_RULE_CF_STATE."
echo "Paper and combined orchestrator schedules remain DISABLED."
echo "Only the read-only watchdog is scheduled; no broker or stocklens-paper change."
if ! aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$STACK" \
  --template-file infra/aws/independent-staging.yaml \
  --parameter-overrides "ArtifactBucket=$ARTIFACT_BUCKET" "ArtifactKey=$ARTIFACT_KEY" "CandidateSignalScheduleState=$SIGNAL_RULE_CF_STATE" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset; then
  show_staging_events
  echo "STOP: failed staging stack was NOT automatically deleted or retried." >&2
  exit 4
fi
aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}' --output json
echo "DEPLOYED_STAGING_ONLY: no live stocklens-paper resources modified."
echo "Running import-only Lambda smoke checks (no Yahoo requests or Paper writes)."
if ! STOCKLENS_EXPECT_ENABLED_SIGNAL="$ACTIVE_MIGRATION" bash infra/aws/smoke_independent_staging.sh; then
  echo "DEPLOYED_BUT_RUNTIME_SMOKE_FAILED: review error; original stocklens-paper remains untouched." >&2
  exit 5
fi
echo "STAGING_RUNTIME_IMPORT_SMOKE_COMPLETE"

