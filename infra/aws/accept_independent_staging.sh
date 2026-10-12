#!/usr/bin/env bash
# Staging only: "probe" checks outbound Yahoo connectivity without writes;
# "signal YYYY-MM-DD" creates one immutable completed-session shadow receipt.
# Never touches stocklens-paper or enables the disabled EventBridge schedule.
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
STACK="stocklens-independent-staging"
FUNCTION="$STACK-candidate"
[[ "$REGION" == eu-central-1 ]] || { echo "REFUSE_NON_STAGING_REGION" >&2; exit 2; }
[[ "$#" == 1 && ( "$1" == probe || "$1" == parity ) || "$#" == 2 && "$1" == signal ]] || {
  echo "Usage: bash infra/aws/accept_independent_staging.sh probe|parity|signal YYYY-MM-DD" >&2
  exit 2
}
mode="$1"
session="${2:-}"
bucket="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidateDataBucket'].OutputValue|[0]" \
  --output text)"
[[ -n "$bucket" && "$bucket" != None ]] || { echo "MISSING_STAGING_BUCKET" >&2; exit 2; }
rule="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='CandidateOrchestratorRuleName'].OutputValue|[0]" \
  --output text)"
[[ "$(aws events describe-rule --region "$REGION" --name "$rule" \
    --query State --output text)" == DISABLED ]] || {
  echo "REFUSE_AUTOMATION_ENABLED" >&2; exit 2;
}
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
payload="$TEMP_DIR/payload.json"
if [[ "$mode" == probe ]]; then
  printf '%s' '{"mode":"STAGING_VENDOR_NETWORK_PROBE"}' >"$payload"
elif [[ "$mode" == parity ]]; then
  printf '%s' '{"mode":"STAGING_SAME_VENDOR_PATH_PARITY"}' >"$payload"
else
  python3 - "$session" "$payload" <<'PY'
import datetime
import json
import sys
from zoneinfo import ZoneInfo
date_str, destination = sys.argv[1:]
try:
    selected = datetime.date.fromisoformat(date_str)
except ValueError as error:
    raise SystemExit(f"INVALID_SESSION_DATE:{error}")
if selected.isoformat() != date_str:
    raise SystemExit("NONCANONICAL_SESSION_DATE")
ny = datetime.datetime.now(ZoneInfo("America/New_York"))
if selected > ny.date() or (selected == ny.date() and ny.time() < datetime.time(18)):
    raise SystemExit(f"STOP_INCOMPLETE_NY_SESSION:{date_str}:current_NY={ny.isoformat()}")
if (ny.date() - selected).days > 5:
    raise SystemExit("STOP_STALE_SIGNAL_SESSION")
with open(destination, "w", encoding="utf-8") as output:
    json.dump({"mode": "STAGING_ONLY", "expected_session": date_str}, output)
PY
fi

aws lambda invoke --region "$REGION" --function-name "$FUNCTION" \
  --cli-binary-format raw-in-base64-out \
  --payload "fileb://$payload" "$TEMP_DIR/response.json" >"$TEMP_DIR/invoke.json"

if ! python3 - "$mode" "$session" "$TEMP_DIR/invoke.json" "$TEMP_DIR/response.json" <<'PY'
import json
import sys
mode, session, invocation, response = sys.argv[1:]
with open(invocation, encoding="utf-8") as f:
    invoke = json.load(f)
with open(response, encoding="utf-8") as f:
    result = json.load(f)
if invoke.get("FunctionError") or invoke.get("StatusCode") != 200:
    print("STAGING_LAMBDA_EXECUTION_FAILED:" + str(result)[:1000])
    sys.exit(1)
expected_status = {
    "probe": "STAGING_VENDOR_NETWORK_OK",
    "parity": "STAGING_SAME_VENDOR_PATH_PARITY_PASS",
    "signal": "STAGED_SIGNAL_ARCHIVED",
}[mode]
if mode == "parity":
    print("PARITY_DIAGNOSTICS:" +
          f"rows={result.get('vendor_rows')}:" +
          f"calendar_equal={result.get('calendar_equal')}:" +
          f"exact_price_mismatches={result.get('mismatch_count')}:" +
          f"max_binary32_ulps={result.get('max_binary32_ulp_distance')}:" +
          f"outside_8_ulps={result.get('outside_binary32_precision_count')}:" +
          f"full_history_policy_mismatches={result.get('policy_mismatch_count')}:" +
          f"decisions_checked={result.get('decisions_compared_count')}:" +
          f"latest_policy_equal={result.get('latest_policy_equal')}:" +
          f"feature_hash_equal={result.get('feature_fingerprints_equal')}")
    if result.get("status") != expected_status:
        print("SAME_VENDOR_PRICE_PARITY_FAILED:" +
              json.dumps(result, sort_keys=True)[:4500])
        sys.exit(1)
if result.get("status") != expected_status or result.get("broker_actions") is not False:
    print("UNEXPECTED_STAGING_RESULT:" + str(result)[:1000])
    sys.exit(1)
if mode == "probe":
    if result.get("market_data_written") is not False or result.get("latest_session_completed") is not False:
        raise SystemExit("VENDOR_PROBE_WAS_NOT_READ_ONLY")
    print("VENDOR_NETWORK_PROBE_PASS:" +
          f"provider={result['provider']}:rows={result['rows']}:" +
          f"latest_vendor_calendar_date={result['last_vendor_calendar_date']}")
    print("NOT_PROVEN:CURRENT_BAR_COMPLETION_OR_INDEPENDENT_VENDOR_PARITY")
elif mode == "parity":
    if (result.get("market_data_written") is not False
        or result.get("second_provider_proven") is not False
        or result.get("decisions_equal") is not True
        or result.get("feature_fingerprints_equal") is not True
        or result.get("calendar_equal") is not True):
        raise SystemExit("SOURCE_PARITY_PROBE_UNSAFE_OR_INCONSISTENT")
    print("SAME_YAHOO_TWO_PATH_PARITY_PASS:" +
          f"completed_session={result['expected_completed_session']}:" +
          f"rows={result['vendor_rows']}:" +
          f"price_precision_class={result['price_precision_classification']}:" +
          f"numeric_exact_mismatch_count={result['mismatch_count']}:" +
          f"policy_mismatch_count={result['policy_mismatch_count']}:" +
          f"dropped_current_partial={result['dropped_incomplete_vendor_current_session']}")
    if result["mismatch_count"]:
        print("NOTE:PRICES_ARE_NOT_IDENTICAL; ONLY_BOUND_AND_POLICY_PARITY_ESTABLISHED")
    print("NOT_PROVEN:SECOND_PROVIDER_INDEPENDENCE_OR_BROKER_FILLS")
else:
    if result.get("session") != session:
        raise SystemExit("WRONG_STAGING_SESSION")
    print("STAGING_SIGNAL_LAMBDA_RETURNED_SUCCESS:" + session)
PY
then
  exit 3
fi
if [[ "$mode" == probe || "$mode" == parity ]]; then
  exit 0
fi

aws s3api get-object --region "$REGION" --bucket "$bucket" \
  --key "market/qqq/$session.csv" \
  "$TEMP_DIR/market.csv" >"$TEMP_DIR/market-meta.json"
aws s3api get-object --region "$REGION" --bucket "$bucket" \
  --key "manifests/qqq/$session.json" \
  "$TEMP_DIR/manifest.json" >"$TEMP_DIR/manifest-meta.json"
aws s3api get-object --region "$REGION" --bucket "$bucket" \
  --key "signals/$session.json" \
  "$TEMP_DIR/signal.json" >"$TEMP_DIR/signal-meta.json"

python3 - "$session" "$TEMP_DIR" <<'PY'
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys

day = sys.argv[1]
d = Path(sys.argv[2])
def load(name):
    return json.loads((d / name).read_text(encoding="utf-8"))
def sha(name):
    return hashlib.sha256((d / name).read_bytes()).hexdigest()
market_meta = load("market-meta.json")
manifest_meta = load("manifest-meta.json")
signal_meta = load("signal-meta.json")
manifest = load("manifest.json")
signal = load("signal.json")
response = load("response.json")
for key in (market_meta, manifest_meta, signal_meta):
    if not key.get("VersionId") or key.get("VersionId") == "null":
        raise SystemExit("S3_OBJECT_VERSION_MISSING")
market = list(csv.DictReader(io.StringIO((d / "market.csv").read_text(encoding="utf-8"))))
if len(market) < 300 or market[-1]["Date"] != day:
    raise SystemExit("MARKET_CSV_SESSION_MISMATCH")
if any(not math.isfinite(float(r["Close"])) or float(r["Close"]) <= 0 for r in market):
    raise SystemExit("INVALID_MARKET_CSV_PRICE")
market_sha = sha("market.csv")
window = "\n".join(f"{r['Date']},{float(r['Close']):.12g}" for r in market[-253:])
window_sha = hashlib.sha256(window.encode("utf-8")).hexdigest()
checks = {
    "manifest_source_checksum": manifest["sha256"] == market_sha,
    "manifest_source_version": manifest["input_version_id"] == market_meta["VersionId"],
    "manifest_source_key": manifest["input_key"] == f"market/qqq/{day}.csv",
    "manifest_provider": manifest["provider"] == "YAHOO_CHART_PUBLIC_ENDPOINT",
    "manifest_type": manifest["data_type"] == "QQQ_ADJUSTED_DAILY",
    "manifest_status": manifest["status"] == "VERIFIED",
    "manifest_completed_session": manifest["audit"]["last_session"] == day,
    "signal_session": signal["latest"]["asof_date"] == day,
    "signal_source_checksum": signal["data_audit"]["source_sha256"] == market_sha,
    "frozen_feature_window_sha": signal["data_audit"]["feature_window_sha256"] == window_sha,
    "signal_shadow_only": signal["mode"] == "SHADOW_ONLY_NO_BROKER_ACTIONS",
    "broker_disabled": signal["execution_plan"]["broker_actions_enabled"] is False,
    "signal_response_sha": response["signal_sha256"] == sha("signal.json"),
    "market_response_version": response["market_version_id"] == market_meta["VersionId"],
    "manifest_response_version": response["manifest_version_id"] == manifest_meta["VersionId"],
    "signal_response_version": response["signal_version_id"] == signal_meta["VersionId"],
}
if not all(checks.values()):
    print("STAGING_RECEIPT_VERIFICATION_FAILED:" +
          ",".join(k for k, valid in checks.items() if not valid))
    sys.exit(1)
latest = signal["latest"]
print("STAGING_SIGNAL_AND_S3_RECEIPT_VERIFIED:" + day)
print("MARKET_ROWS=" + str(len(market)) +
      " LEVEL=" + str(latest["level"]) +
      " DEFENSE=" + str(latest["defense_active"]) +
      " LEVERAGE=" + str(latest["target_leverage"]) +
      " ACTION=" + str(signal["action"]))
print("BROKER_DISABLED:YES; PROVENANCE_INTERNAL_SHA_CHAIN:YES")
print("NOT_PROVEN:SECOND_PROVIDER_PARITY_OR_PROSPECTIVE_PAPER_EXECUTION")
PY
