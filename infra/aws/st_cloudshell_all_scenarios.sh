#!/usr/bin/env bash
# StockLens ST: execute real public Paper fault tests and live read-only AWS audit.
# Run from a SHA-pinned git checkout in AWS CloudShell. NO AWS mutations/invokes.
set -uo pipefail
export AWS_DEFAULT_REGION=eu-central-1 AWS_REGION=eu-central-1 AWS_PAGER=""
SESSION="2026-11-17"
INSTALL=1
while (( $# )); do
  case "$1" in
    --session) SESSION="$2"; shift 2 ;;
    --skip-install) INSTALL=0; shift ;;
    *) echo "ERROR: unknown parameter: $1" >&2; exit 2 ;;
  esac
done
[[ "$SESSION" =~ ^20[0-9]{2}-[0-9]{2}-[0-9]{2}$ ]] || { echo "BAD_SESSION" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 2
AWS_ACCOUNT="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)" || {
  echo "AWS_IDENTITY_NOT_AVAILABLE" >&2; exit 2;
}
[[ "$AWS_ACCOUNT" == "634740393398" ]] || {
  echo "WRONG_AWS_ACCOUNT:$AWS_ACCOUNT" >&2; exit 2;
}
echo "ACCOUNT_OK:$AWS_ACCOUNT:eu-central-1"
RUNTIME="$HOME/.stocklens-st-console-qa"
mkdir -p "$RUNTIME"
if (( INSTALL )); then
  python3 -m venv --system-site-packages "$RUNTIME/venv" || exit 2
  "$RUNTIME/venv/bin/python" -m pip install --disable-pip-version-check -q \
    'pytest>=8,<10' 'pandas>=2,<3' 'exchange-calendars>=4,<5' \
    'yfinance>=0.2.60,<1' 'boto3>=1.34,<2' || exit 2
fi
PYTHON="$RUNTIME/venv/bin/python"
[[ -x "$PYTHON" ]] || { echo "VENV_MISSING_RUN_WITHOUT_SKIP_INSTALL" >&2; exit 2; }
export PYTHONPATH="$ROOT:$ROOT/infra/aws"
"$PYTHON" - "$SESSION" <<'PY' || exit 2
import sys
from datetime import datetime,timezone
import exchange_calendars as xcals
s=sys.argv[1]
cal=xcals.get_calendar("XNYS")
if not cal.is_session(s):
    raise SystemExit("SESSION_NOT_XNYS:"+s)
if datetime.now(timezone.utc) <= cal.session_close(s).to_pydatetime():
    raise SystemExit("SESSION_NOT_COMPLETED_USE_PREVIOUS_XNYS_DAY:"+s)
print("COMPLETED_XNYS_SESSION_CONFIRMED:"+s)
PY

# Actual public source module tests: fake vendor delays/missing bars,
# holidays/half-days, immutable ledger crashes, accounting, AWS alarm/schedule mocks.
# This does NOT exercise private deployed Paper Lambda code.
echo "===== OFFLINE REAL-MODULE FAULT INJECTION ====="
"$PYTHON" -m pytest -q --disable-warnings \
  tests/test_st_paper_operational_blockers_readonly.py \
  tests/test_st_paper_closeout_readonly.py \
  tests/test_paper_eod_completeness.py \
  tests/test_paper_transaction_recovery.py \
  tests/test_paper_session_continuity.py \
  tests/test_paper_portfolio_integrity.py \
  tests/test_paper_execution_contract.py \
  tests/test_aws_schedule_watchdog.py \
  tests/test_paper_forward_audit.py \
  tests/test_paper_reconcile_frozen_contract.py
TEST_EXIT=$?
echo "OFFLINE_TEST_EXIT=$TEST_EXIT"

# Actual authenticated AWS inspection, NEVER calls Lambda invoke or writes S3.
echo "===== ACTUAL AWS ST READ-ONLY STATE ====="
REPORT="$RUNTIME/st-aws-$SESSION.json"
"$PYTHON" infra/aws/st_paper_operational_blockers_readonly.py \
  --session "$SESSION" > "$REPORT"
AUDIT_EXIT=$?
cat "$REPORT"
"$PYTHON" - "$REPORT" "$TEST_EXIT" "$AUDIT_EXIT" <<'PY'
import json,sys
o=json.load(open(sys.argv[1]))
tests=int(sys.argv[2]);audit=int(sys.argv[3])
status=o.get("status")
blocked=o.get("blockers",[])
print("===== CLEAR SEPARATE VERDICTS =====")
print("OFFLINE_PUBLIC_CODE_FAULT_TESTS:", "PASS" if tests==0 else "FAIL")
print("LIVE_AWS_READBACK:",status)
print("LIVE_AWS_BLOCKERS:",",".join(blocked) if blocked else "none-visible")
print("LIVE_PAPER_RECOVERY_ATTESTED:FALSE")
print("BROKER_ORDERS:FALSE  AWS_MUTATIONS:FALSE  LAMBDA_INVOCATIONS:FALSE")
if audit or status=="DIAGNOSTIC_UNVERIFIED":
    raise SystemExit(2)
if tests:
    raise SystemExit(3)
if status!="NO_OBVIOUS_BLOCKERS_NOT_PAPER_ACCEPTANCE":
    raise SystemExit(4)
PY
exit $?
