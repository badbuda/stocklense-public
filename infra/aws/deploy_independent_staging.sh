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
COMMIT="$(git rev-parse HEAD)"
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

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
python3 - "$TEMP_DIR/candidate.zip" <<'PY'
import sys, zipfile
from pathlib import Path
paths = [
    "infra/aws/independent_market_ingest.py",
    "infra/aws/independent_pipeline.py",
    "infra/aws/independent_signal_producer.py",
    "stocklens/core.py",
    "stocklens/__init__.py",
]
with zipfile.ZipFile(sys.argv[1], "w", compression=zipfile.ZIP_DEFLATED) as out:
    for file in paths:
        if not Path(file).is_file():
            raise RuntimeError(f"MISSING_PACKAGE_FILE:{file}")
        out.write(file, file)
PY
DIGEST="$(sha256sum "$TEMP_DIR/candidate.zip" | cut -d' ' -f1)"
ARTIFACT_KEY="candidate/${COMMIT}/${DIGEST}.zip"
if ! aws s3api head-object --bucket "$ARTIFACT_BUCKET" \
  --key "$ARTIFACT_KEY" >/dev/null 2>&1; then
  aws s3api put-object --bucket "$ARTIFACT_BUCKET" \
    --key "$ARTIFACT_KEY" --body "$TEMP_DIR/candidate.zip" \
    --if-none-match '*' --server-side-encryption AES256 >/dev/null
fi
aws cloudformation validate-template \
  --template-body file://infra/aws/independent-staging.yaml >/dev/null

echo "STAGING ONLY: ${STACK}; source commit ${COMMIT}; ZIP sha256 ${DIGEST}"
echo "This creates a separate S3 bucket, read/write-scoped role and"
echo "manual-invocation Lambda; it creates NO schedule or broker access."
aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$STACK" \
  --template-file infra/aws/independent-staging.yaml \
  --parameter-overrides "ArtifactBucket=$ARTIFACT_BUCKET" "ArtifactKey=$ARTIFACT_KEY" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset
aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}' --output json
echo "DEPLOYED_STAGING_ONLY: no live stocklens-paper resources modified."
