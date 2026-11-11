#!/usr/bin/env bash
# Read-only multi-gate ST audit; does not bootstrap, enable schedules, or broker orders.
set -uo pipefail
export AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1 AWS_PAGER=""
SESSION="${1:-2026-10-30}"
[[ "$SESSION" =~ ^2026-[0-9]{2}-[0-9]{2}$ ]] || { echo BAD_SESSION; exit 2; }
[[ "$(aws sts get-caller-identity --query Account --output text 2>/dev/null)" == 634740393398 ]] || { echo WRONG_AWS_ACCOUNT; exit 2; }
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
BASE="https://raw.githubusercontent.com/badbuda/stocklense-public/main/infra/aws"
fetch_pinned() {
  local name="$1" sha="$2"
  curl -fsSL --retry 3 "$BASE/$name" -o "$D/$name" || return 1
  [[ "$(git hash-object "$D/$name")" == "$sha" ]] || { echo "HASH_MISMATCH:$name"; return 1; }
}
fetch_pinned stocklens_st_signal_acceptance.py 9dd5e6647edff384f66736dee48135cb85618663 || exit 3
fetch_pinned stocklens_st_paper_bootstrap.py 3195430d909edc5db4293d26e939f86c86b1ead2 || exit 3
fetch_pinned stocklens_st_prod_readonly_audit.py 80cef3947604cac7831727a04e506ec735b46a41 || exit 3
echo "=== ST/PROD READ-ONLY INFRA ==="
python3 "$D/stocklens_st_prod_readonly_audit.py"; A=$?
echo "=== COMPLETED 2026-10-29 SIGNAL ACCEPTANCE ==="
python3 "$D/stocklens_st_signal_acceptance.py" --session 2026-10-29; B=$?
echo "=== PROSPECTIVE PAPER STATUS $SESSION ==="
python3 "$D/stocklens_st_paper_bootstrap.py" status --session "$SESSION"; C=$?
echo "=== PROSPECTIVE PAPER PREFLIGHT $SESSION ==="
python3 "$D/stocklens_st_paper_bootstrap.py" check --session "$SESSION"; E=$?
printf "INFRA=%s SIGNAL=%s STATUS=%s PREFLIGHT=%s\n" "$A" "$B" "$C" "$E"
echo "NO_AWS_WRITES_NO_PAPER_BOOTSTRAP_NO_PROD_CHANGES_NO_BROKER"
if (( A || B || C || E )); then echo "PENDING_OR_BLOCKED:NO_MUTATION"; exit 2; fi
echo "READ_ONLY_GATES_PASS:GENESIS_NOT_CREATED:SCHEDULE_NOT_ENABLED"
