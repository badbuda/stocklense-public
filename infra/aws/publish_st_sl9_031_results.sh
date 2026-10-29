#!/usr/bin/env bash
# ST ONLY: pinned historical research results, create-only S3 write, readback SHA.
# Does not invoke Lambdas, modify PROD, schedules, IAM, Paper or broker.
set -euo pipefail
export AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1 AWS_PAGER=""
mode="${1:-inspect}"
case "$mode" in inspect|publish|verify) ;; *) echo "USE inspect|publish|verify";exit 2;; esac
approval_mode=interactive
if [[ "$mode" == publish && "${2:-}" == "--confirm" ]]; then
  # Explicit one-line CLI consent avoids CloudShell mobile/embedded-TTY read bugs.
  [[ "$#" == 3 && "${3:-}" == PUBLISH_ST_RESEARCH_ONLY ]] || {
    echo "NOT_AUTHORIZED_NO_WRITES:INVALID_CLI_CONFIRMATION";exit 4;
  }
  approval_mode=command_line
elif [[ "$#" -gt 1 ]]; then
  echo "USAGE: inspect | verify | publish [--confirm PUBLISH_ST_RESEARCH_ONLY]"
  exit 2
fi
for cmd in aws curl git python3 sha256sum; do command -v "$cmd" >/dev/null || exit 2;done
ACCOUNT=634740393398
ST=stocklens-st
BUCKET=stocklens-st-candidatedata-6jj7i9fxjmfr
REF=8fe5ebdb7f7e2d3a9bc6bc9109d2b2745aae9bea
JSON_BLOB=afca16734fbb4bdc340c42b9e10f727d3ac2f573
CSV_BLOB=e6d4825d8f697b0704e8886171f26561043acb99
PREFIX="research/experiments/SL9-031/$REF"
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || { echo WRONG_ACCOUNT;exit 3; }
state="$(aws cloudformation describe-stacks --stack-name "$ST" --query 'Stacks[0].StackStatus' --output text)"
[[ "$state" == CREATE_COMPLETE || "$state" == UPDATE_COMPLETE ]] || { echo UNHEALTHY_ST_STACK;exit 3; }
output() {
  aws cloudformation describe-stacks --stack-name "$ST" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue|[0]" --output text
}
[[ "$(output CandidateDataBucket)" == "$BUCKET" ]] || { echo WRONG_ST_BUCKET;exit 3; }
[[ "$(aws s3api get-bucket-versioning --bucket "$BUCKET" --query Status --output text)" == Enabled ]] || { echo S3_VERSIONING_OFF;exit 3; }
public="$(aws s3api get-public-access-block --bucket "$BUCKET" --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' --output text)"
[[ "$public" == $'True\tTrue\tTrue\tTrue' ]] || { echo ST_S3_PUBLIC_BLOCK_MISSING;exit 3; }
for resource in CandidateSignalOnlyRuleName CandidatePaperOnlyRuleName CandidateOrchestratorRuleName; do
 rule="$(output "$resource")"
 [[ "$rule" != None && -n "$rule" ]] || { echo RULE_NOT_FOUND;exit 3; }
 [[ "$(aws events describe-rule --name "$rule" --query State --output text)" == DISABLED ]] || { echo ST_SCHEDULE_ACTIVE_REFUSE:$resource;exit 3; }
done
for file in st-combo-results.json st-combo-curves.csv; do
 curl --fail --silent --show-error --location --retry 3 \
    "https://raw.githubusercontent.com/badbuda/stocklense-public/$REF/docs/$file" \
    --output "$root/$file"
done
[[ "$(git hash-object "$root/st-combo-results.json")" == "$JSON_BLOB" ]] || { echo JSON_SOURCE_BLOB_MISMATCH;exit 4; }
[[ "$(git hash-object "$root/st-combo-curves.csv")" == "$CSV_BLOB" ]] || { echo CSV_SOURCE_BLOB_MISMATCH;exit 4; }
python3 - "$root/st-combo-results.json" "$root/st-combo-curves.csv" <<'PY'
import csv,json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
with open(sys.argv[2],encoding="utf-8",newline="") as f:
 rows=list(csv.reader(f))
if not (x.get("kind")=="SL9_031_ST_REAL_ETF_OVERLAY_COMBINATIONS"
        and x.get("case_count")==56 and x.get("stress_runs")==224
        and len(x.get("results",[]))==56 and len(x.get("stress",{}))==56
        and x.get("frozen_daily_parity_all_stress_cases") is True
        and x.get("broker_actions") is False
        and x.get("automatic_promotion") is False
        and x.get("aws_st_paper_runs") is False
        and x.get("source_independently_audited") is False
        and len(rows)==x["period"]["sessions"]+1
        and rows[0][0]=="date"
        and rows[-1][0]==x["period"]["end"]):
 raise SystemExit("SOURCE_EVIDENCE_OR_CURVES_INVALID")
print("PINNED_ST_HISTORICAL_RESEARCH_VERIFIED:56:224")
PY
echo "ST_ONLY_READY:bucket=$BUCKET:prefix=$PREFIX:mode=$mode"
if [[ "$mode" == inspect ]];then
 echo "INSPECT_READ_ONLY_NO_AWS_MUTATIONS"
 exit 0
fi
verify_object() {
 local key="$1" src="$2" dst="$root/verified-$(basename "$2")"
 aws s3api get-object --bucket "$BUCKET" --key "$key" "$dst" >/dev/null
 [[ "$(sha256sum "$dst" | cut -d' ' -f1)" == "$(sha256sum "$src" | cut -d' ' -f1)" ]] || {
   echo AWS_ST_OBJECT_CONTENT_MISMATCH:"$key" >&2; exit 4;
 }
 id="$(aws s3api head-object --bucket "$BUCKET" --key "$key" --query VersionId --output text)"
 [[ -n "$id" && "$id" != None ]] || { echo S3_VERSION_ID_MISSING;exit 4; }
 echo "ST_READBACK_SHA_VERIFIED:$key:version=$id"
}
publish_one() {
 local key="$1" src="$2" content_type="$3"
 local err="$root/head-$(basename "$src").stderr"
 if aws s3api head-object --bucket "$BUCKET" --key "$key" >/dev/null 2>"$err"; then
   # A previous partial publication can be continued, but NEVER overwritten.
   verify_object "$key" "$src"
   echo "EXISTING_PINNED_ST_OBJECT_REUSED:$key"
 elif grep -Eqi '\\(404\\)|NoSuchKey|Not Found' "$err"; then
   aws s3api put-object --bucket "$BUCKET" --key "$key" \
     --body "$src" --content-type "$content_type" --if-none-match '*' \
     --metadata "study=SL9-031,source=$REF" >/dev/null
   echo "CREATED_NEW_PINNED_ST_OBJECT:$key"
 else
   echo "ST_S3_HEAD_DENIED_OR_UNKNOWN_NO_WRITE:$key" >&2
   exit 4
 fi
}
if [[ "$mode" == publish ]];then
 if [[ "$approval_mode" == interactive ]]; then
   # Always read from the controlling terminal, never the enclosing multiline
   # shell block. A mobile keyboard may send a trailing carriage return.
   if [[ ! -r /dev/tty ]]; then
     echo "NO_INTERACTIVE_TTY:USE_publish_--confirm_PUBLISH_ST_RESEARCH_ONLY"
     exit 4
   fi
   approval=""
   IFS= read -r -p 'Confirm ST-only new historical S3 research objects (AWS charges possible). Type PUBLISH_ST_RESEARCH_ONLY: ' approval </dev/tty || {
     echo "NOT_AUTHORIZED_NO_WRITES:TTY_READ_FAILED";exit 4;
   }
   [[ "$approval" =~ ^[[:space:]]*PUBLISH_ST_RESEARCH_ONLY[[:space:]]*$ ]] || {
     echo "NOT_AUTHORIZED_NO_WRITES:TTY_INPUT_MISMATCH";exit 4;
   }
 fi
 echo "EXPLICIT_ST_ONLY_PUBLICATION_CONSENT_VERIFIED"
 publish_one "$PREFIX/results.json" "$root/st-combo-results.json" application/json
 publish_one "$PREFIX/curves.csv" "$root/st-combo-curves.csv" text/csv
fi
verify_object "$PREFIX/results.json" "$root/st-combo-results.json"
verify_object "$PREFIX/curves.csv" "$root/st-combo-curves.csv"
echo "ST_S3_SL9_031_PUBLISH_AND_VERIFY_PASS:NO_PROD_NO_PAPER_NO_BROKER"
