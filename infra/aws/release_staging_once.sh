#!/usr/bin/env bash
# ONE pinned, operator-reviewed STAGING-only release (not production cutover).
# Leaves both independent trading rules and old orchestrator DISABLED.
# Usage: EXPECTED_STOCKLENS_RELEASE_COMMIT=<GREEN_SHA> bash infra/aws/release_staging_once.sh
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-eu-central-1}"
[[ "$AWS_REGION" == eu-central-1 ]] || { echo "REFUSE_NON_STAGING_REGION" >&2; exit 2; }
[[ -n "${EXPECTED_STOCKLENS_RELEASE_COMMIT:-}" &&
   "${EXPECTED_STOCKLENS_RELEASE_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "REQUIRE_EXACT_GREEN_CI_COMMIT_SHA_FOR_RELEASE" >&2; exit 2;
}
[[ -f infra/aws/independent-staging.yaml && -f ci_transfer_manifest.json ]] || {
  echo "RUN_FROM_REPOSITORY_ROOT" >&2; exit 2;
}
command -v git >/dev/null && command -v python3 >/dev/null || {
  echo "MISSING_RELEASE_COMMAND" >&2; exit 2;
}
actual="$(git rev-parse HEAD)"
[[ "$actual" == "$EXPECTED_STOCKLENS_RELEASE_COMMIT" ]] || {
  echo "REFUSE_NON_PINNED_RELEASE:$actual" >&2; exit 2;
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "REFUSE_DIRTY_RELEASE_REPOSITORY" >&2; exit 2;
}
python3 ci_transfer_guard.py
echo "PINNED_LOCAL_RELEASE_GUARD_PASS:$actual"
echo "DEPLOYING_ONE_ISOLATED_STAGING_STACK; NO BROKER/PRODUCTION CUTOVER"
bash infra/aws/deploy_independent_staging.sh
echo "RUNNING_READ_ONLY_POST_DEPLOY_RELEASE_AUDIT"
bash infra/aws/audit_staging_release.sh
echo "STAGING_CODE_DEPLOYED_AND_INFRA_AUDITED; SCHEDULE_ACTIVATION_NEEDS_SEPARATE_REAL_EMAIL_AND_MARKET_EVIDENCE"
