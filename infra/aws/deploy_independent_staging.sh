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
# Paper uses exact frozen yfinance, pandas and exchange_calendars code paths.
# Native wheels MUST target the same CPython version as the Lambda runtime.
PY312="${PY312:-python3.12}"
if ! command -v "$PY312" >/dev/null; then
  echo "Python 3.12 is required to package the candidate's native wheels" >&2; exit 2
fi
"$PY312" - <<'PY'
import sys
assert sys.version_info[:2] == (3, 12), "Expected CPython 3.12 for Lambda x86_64"
PY
"$PY312" -m pip install --disable-pip-version-check --prefer-binary \
  --no-compile --target "$TEMP_DIR/deps" -r requirements.txt

"$PY312" - "$TEMP_DIR/candidate.zip" "$TEMP_DIR/deps" <<'PY'
import sys, zipfile
from pathlib import Path

paths = [
    "infra/aws/independent_market_ingest.py",
    "infra/aws/independent_pipeline.py",
    "infra/aws/independent_orchestrator.py",
    "infra/aws/independent_signal_producer.py",
    "infra/aws/independent_paper.py",
    "stocklens/core.py",
    "stocklens/paper.py",
    "stocklens/__init__.py",
    "paper_rebalance_math.py",
    "paper_portfolio_integrity.py",
]
deps = Path(sys.argv[2])
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
echo "This creates a private bucket, THREE candidate Lambdas and an"
echo "EventBridge rule that is DISABLED. No broker or stocklens-paper change."
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
