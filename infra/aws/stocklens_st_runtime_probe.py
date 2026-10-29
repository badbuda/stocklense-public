#!/usr/bin/env python3
"""Two safe immediate runtime probes for the already ENABLED isolated ST Signal.

Calls only STAGING_IMPORT_SMOKE and STAGING_VENDOR_NETWORK_PROBE, both
read-only modes in the pinned deployed StockLens Lambda. Does not generate
any historical or current session Signal and never bootstraps Paper.
"""
from __future__ import annotations
import json
import argparse
from pathlib import Path
import subprocess
import tempfile
import sys

ACCOUNT = "634740393398"
REGION = "eu-central-1"
STACK = "stocklens-st"
SOURCE = "stocklens-independent-staging"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
FUNCTION = STACK + "-candidate"


def aws(service, op, *args):
    p = subprocess.run(["aws","--region",REGION,"--no-cli-pager","--output","json","--cli-read-timeout","180",
                        service,op,*args],capture_output=True,text=True,timeout=150)
    if p.returncode:
        raise RuntimeError("AWS_PROBE_FAILED:"+service+"/"+op+":"+p.stderr[:250])
    return json.loads(p.stdout)


def stack(name):
    o=aws("cloudformation","describe-stacks","--stack-name",name)
    if len(o.get("Stacks",[]))!=1 or o["Stacks"][0]["StackStatus"] not in ("CREATE_COMPLETE","UPDATE_COMPLETE"):
        raise RuntimeError("UNSTABLE_STACK:"+name)
    return {x["OutputKey"]:x["OutputValue"] for x in o["Stacks"][0].get("Outputs",[])}


def preconditions():
    if aws("sts","get-caller-identity").get("Account")!=ACCOUNT:
        raise RuntimeError("WRONG_AWS_ACCOUNT")
    st=stack(STACK)
    old=stack(SOURCE)
    if st.get("CandidateDataBucket")!=BUCKET or st.get("CandidateFunctionName")!=FUNCTION:
        raise RuntimeError("WRONG_ISOLATED_ST_RESOURCES")
    for key,state in (("CandidateSignalOnlyRuleName","ENABLED"),
                      ("CandidatePaperOnlyRuleName","DISABLED"),
                      ("CandidateOrchestratorRuleName","DISABLED")):
        rule=st.get(key)
        if not rule or aws("events","describe-rule","--name",rule).get("State")!=state:
            raise RuntimeError("UNSAFE_EVENTBRIDGE_STATE:"+key)
    cfg=aws("lambda","get-function-configuration","--function-name",FUNCTION)
    source=aws("lambda","get-function-configuration",
               "--function-name",old["CandidateFunctionName"])
    if (cfg.get("State")!="Active" or cfg.get("LastUpdateStatus")!="Successful"
        or cfg.get("Handler")!="infra.aws.independent_pipeline.handler"
        or cfg.get("Environment",{}).get("Variables",{}).get("STOCKLENS_DATA_BUCKET")!=BUCKET
        or cfg.get("CodeSha256")!=source.get("CodeSha256")
        or not cfg.get("CodeSha256")):
        raise RuntimeError("WRONG_LAMBDA_HANDLER_BUCKET_OR_CODE_SHA")
    print("ST_SAFE_RUNTIME_CODE_PARITY_PASS:signal_enabled:paper_disabled:prod_untouched")


def probe(fn_mode, expected):
    with tempfile.TemporaryDirectory(prefix="stocklens-st-safe-probe-") as d:
        payload=Path(d)/"request.json"
        response=Path(d)/"response.json"
        payload.write_text(json.dumps({"mode":fn_mode}),encoding="utf-8")
        meta=aws("lambda","invoke","--function-name",FUNCTION,
                 "--cli-binary-format","raw-in-base64-out",
                 "--payload","fileb://"+str(payload),str(response))
        try:
            data=json.loads(response.read_text(encoding="utf-8"))
        except (OSError,ValueError):
            raise RuntimeError("ST_READ_ONLY_PROBE_INVALID_RESPONSE:"+fn_mode)
        if (meta.get("StatusCode")!=200 or meta.get("FunctionError")
            or data.get("status")!=expected
            or data.get("broker_actions") is not False
            or data.get("market_data_written") is not False):
            raise RuntimeError("ST_READ_ONLY_PROBE_UNVERIFIED:"+fn_mode+":"+str(data)[:700])
        if fn_mode=="STAGING_VENDOR_NETWORK_PROBE":
            if (data.get("provider")!="YAHOO_CHART_PUBLIC_ENDPOINT"
                or type(data.get("rows")) is not int or data["rows"]<300
                or data.get("latest_session_completed") is not False):
                raise RuntimeError("ST_READ_ONLY_VENDOR_PROBE_BAD_METADATA")
        print("PASS:"+fn_mode+":broker=false:s3_writes=false")
        if fn_mode=="STAGING_VENDOR_NETWORK_PROBE":
            print("VENDOR_OBSERVED_METADATA:rows="+str(data["rows"])+
                  ":last_calendar_date="+str(data["last_vendor_calendar_date"]))


def same_vendor_parity():
    """Diagnostic comparison of two Yahoo-family paths, never a second vendor."""
    with tempfile.TemporaryDirectory(prefix="stocklens-st-parity-") as d:
        payload=Path(d)/"request.json"
        output=Path(d)/"response.json"
        payload.write_text(json.dumps({"mode":"STAGING_SAME_VENDOR_PATH_PARITY"}),
                           encoding="utf-8")
        meta=aws("lambda","invoke","--function-name",FUNCTION,
                 "--cli-binary-format","raw-in-base64-out",
                 "--payload","fileb://"+str(payload),str(output))
        try:
            data=json.loads(output.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise RuntimeError("ST_PARITY_INVALID_LAMBDA_JSON") from exc
        if (meta.get("StatusCode")!=200 or meta.get("FunctionError")
            or data.get("broker_actions") is not False
            or data.get("market_data_written") is not False
            or data.get("second_provider_proven") is not False
            or data.get("provider")!="YAHOO_CHART_VS_YFINANCE_YAHOO_AUTO_ADJUST"):
            raise RuntimeError("ST_SAME_VENDOR_PARITY_NOT_TRUSTWORTHY:"+str(data)[:700])
        summary={key:data.get(key) for key in (
            "status","expected_completed_session","vendor_rows","reference_rows",
            "mismatch_count","outside_binary32_precision_count",
            "max_binary32_ulp_distance","numeric_rounding_compatible",
            "calendar_equal","feature_fingerprints_equal","decisions_equal",
            "policy_mismatch_count","latest_action_equal","second_provider_proven",
            "max_absolute_price_difference","max_relative_price_difference",
            "first_outside_precision_budget","latest_feature_absolute_differences",
            "first_mismatches","last_date","vendor_feature_sha256",
            "reference_feature_sha256")}
        print("ST_SAME_VENDOR_PARITY_DIAGNOSTIC:"+json.dumps(summary,sort_keys=True))
        if (data.get("status")!="STAGING_SAME_VENDOR_PATH_PARITY_PASS"
            or data.get("calendar_equal") is not True
            or data.get("numeric_rounding_compatible") is not True
            or data.get("feature_fingerprints_equal") is not True
            or data.get("decisions_equal") is not True
            or data.get("latest_action_equal") is not True):
            raise RuntimeError("ST_SAME_VENDOR_PARITY_BLOCKED_NOT_SECOND_PROVIDER")
        print("ST_SAME_VENDOR_PARITY_PASS:SECOND_INDEPENDENT_VENDOR_STILL_NOT_PROVEN")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--parity",action="store_true",
                   help="also compare Yahoo-chart versus yfinance paths, read-only")
    args=p.parse_args()
    preconditions()
    probe("STAGING_IMPORT_SMOKE","STAGING_IMPORT_OK")
    probe("STAGING_VENDOR_NETWORK_PROBE","STAGING_VENDOR_NETWORK_OK")
    if args.parity:
        same_vendor_parity()
    print("ST_SIGNAL_IMPORT_AND_VENDOR_NETWORK_PASS:NO_SIGNAL_GENERATED:NO_PAPER_NO_PROD_NO_BROKER")


if __name__=="__main__":
    try:main()
    except Exception as e:
        print("ST_SIGNAL_READ_ONLY_PROBE_BLOCKED:"+str(e))
        sys.exit(2)
