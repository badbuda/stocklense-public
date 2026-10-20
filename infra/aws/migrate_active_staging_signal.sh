#!/usr/bin/env bash
# Recover the already activated signal-only Staging stack using one pinned
# CloudFormation update. NEVER deploy via the unguarded CloudFormation defaults.
# Does not enable Paper, bootstrap a book, or touch stocklens-paper.
set -euo pipefail
export AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1 AWS_PAGER=""
[[ -f infra/aws/independent-staging.yaml && -f ci_transfer_manifest.json ]] || {
  echo "RUN_FROM_STOCKLENS_STAGING_REPO_ROOT" >&2; exit 3;
}
[[ "${EXPECTED_STOCKLENS_RELEASE_COMMIT:-}" =~ ^[a-f0-9]{40}$ ]] || {
  echo "REQUIRE_PINNED_GREEN_CI_SHA" >&2; exit 3;
}
[[ "$(git rev-parse HEAD)" == "$EXPECTED_STOCKLENS_RELEASE_COMMIT" ]] || {
  echo "REFUSE_DIFFERENT_HEAD" >&2; exit 3;
}
[[ -z "$(git status --porcelain)" ]] || { echo "REFUSE_DIRTY_GIT_TREE" >&2; exit 3; }
[[ "$(aws sts get-caller-identity --query Account --output text)" == 634740393398 ]] || {
  echo "WRONG_AWS_ACCOUNT" >&2; exit 3;
}
python3 ci_transfer_guard.py
# Validates SNS confirmation, active Signal and disabled Paper/orchestrator
# without making any AWS mutations.
bash infra/aws/enable_staging_signal_only.sh check
echo "This updates only stocklens-independent-staging, packaging pinned code."
echo "It preserves the existing enabled Signal and versioned monitoring anchor,"
echo "reschedules Signal to 02:30Z, Paper rule stays DISABLED; no broker calls."
echo "A CloudFormation failure could affect the old Signal rule; review AWS"
echo "stack events and restore the prior rule only through audited recovery."
read -r -p "Type MIGRATE_ACTIVE_STAGING_SIGNAL_ONLY to deploy: " answer
[[ "$answer" == MIGRATE_ACTIVE_STAGING_SIGNAL_ONLY ]] || {
  echo "OPERATOR_DID_NOT_AUTHORIZE_MIGRATION" >&2; exit 3;
}
STOCKLENS_ACTIVE_SIGNAL_MIGRATION=1 bash infra/aws/deploy_independent_staging.sh
# The inner deploy runs all five read-only import smoke checks and verifies
# EventBridge schedules + immutable marker after the CF stack has updated.
echo "ACTIVE_STAGING_SIGNAL_MIGRATION_DEPLOYED_IMPORTS_PASS"
echo "NOT_PROVEN:market_session_success_or_contiguous_paper_or_vendor_parity"
echo "INCIDENT:2026-10-19_SIGNAL_MISSING_MUST_REMAIN_IN_AUDIT"
