import boto3,csv,hashlib,io,json,os,urllib.request
from botocore.exceptions import ClientError
from datetime import datetime,time,timezone
from zoneinfo import ZoneInfo

ROOT="https://raw.githubusercontent.com/badbuda/stocklense-public/main/"
def read(path):
    req=urllib.request.Request(ROOT+path,headers={"User-Agent":"StockLens-Paper-Audit/1"})
    with urllib.request.urlopen(req,timeout=12) as r: b=r.read(200001)
    if len(b)>200000: raise ValueError("EVIDENCE_TOO_LARGE")
    return b

def evidence(now,report,ledger,trades,prior,current):
    local=now.astimezone(ZoneInfo("America/New_York"))
    day=local.date().isoformat()
    if local.weekday()>4 or local.time()<time(18,0):
        raise RuntimeError("NOT_COMPLETED_MARKET_DAY")
    if report.get("status")!="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS":
        raise RuntimeError("INDEPENDENT_PAPER_AUDIT_NOT_PASS")
    if report.get("latest_session")!=day or report.get("broker_fills_observed") is not False:
        raise RuntimeError("MISSING_PROSPECTIVE_PAPER")
    if current.get("latest",{}).get("asof_date")!=day or current.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("MISSING_CURRENT_SHADOW_SIGNAL")
    rows=list(csv.DictReader(io.StringIO(ledger)))
    if not rows or rows[-1].get("session_date")!=day or sum(r["session_date"]==day for r in rows)!=1:
        raise RuntimeError("NO_UNIQUE_CURRENT_LEDGER_ROW")
    row=rows[-1]
    if row.get("execution_source")!="YFINANCE_1M_RAW":
        raise RuntimeError("NONOBSERVED_ETF_BAR_SOURCE")
    signal=row.get("signal_date","")
    if signal>=day or prior.get("latest",{}).get("asof_date")!=signal or prior.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("PRIOR_FROZEN_SIGNAL_INVALID")
    issued=datetime.fromisoformat(prior["generated_at_utc"].replace("Z","+00:00"))
    opening=datetime.fromisoformat(day+"T09:30:00").replace(tzinfo=ZoneInfo("America/New_York"))
    if issued.tzinfo is None or issued>=opening:
        raise RuntimeError("PRIOR_SIGNAL_WAS_LATE")
    for k in ("qqq_weight","tqqq_weight"):
        if abs(float(prior["latest"][k])-float(row["target_"+k]))>1e-9:
            raise RuntimeError("FROZEN_TARGET_MISMATCH")
    matched=[t for t in csv.DictReader(io.StringIO(trades)) if t.get("execution_session")==day]
    if len(matched)!=int(row["trade_count_session"]):
        raise RuntimeError("MISSING_PAPER_TRADE_RECEIPT")
    for t in matched:
        if t.get("symbol") not in ("QQQ","TQQQ") or t.get("side") not in ("BUY","SELL"):
            raise RuntimeError("UNEXPECTED_INSTRUMENT")
        if t.get("signal_date")!=signal or t.get("time_et")!=("09:31" if t["side"]=="SELL" else "09:32"):
            raise RuntimeError("TRADE_WINDOW_OR_SIGNAL_INVALID")
    return day,row,matched

def handler(event,context):
    now=datetime.now(timezone.utc)
    report=json.loads(read("docs/paper_portfolio_integrity.json"))
    ledger=read("paper_portfolio/ledger.csv").decode()
    trades=read("paper_portfolio/trades.csv").decode()
    current=json.loads(read("shadow_history/latest.json"))
    rows=list(csv.DictReader(io.StringIO(ledger)))
    if not rows: raise RuntimeError("NO_PAPER_SESSION")
    prior=json.loads(read("shadow_history/"+rows[-1]["signal_date"]+".json"))
    day,row,matched=evidence(now,report,ledger,trades,prior,current)
    payload=json.dumps({"row":row,"trades":matched},sort_keys=True,separators=(",",":"))
    item={"session_date":{"S":day+"#PAPER"},"paper_evidence_json":{"S":payload},
          "paper_sha256":{"S":hashlib.sha256(payload.encode()).hexdigest()},
          "broker_orders_authorized":{"BOOL":False},"broker_fills_observed":{"BOOL":False}}
    try:
        boto3.client("dynamodb").put_item(TableName=os.environ["TABLE_NAME"],
            Item=item,ConditionExpression="attribute_not_exists(session_date)")
        status="PAPER_EVIDENCE_STORED"
    except ClientError as exc:
        if exc.response.get("Error",{}).get("Code")!="ConditionalCheckFailedException": raise
        status="DUPLICATE_IMMUTABLE_NOT_OVERWRITTEN"
    print(json.dumps({"status":status,"session":day,"actual_broker_fills":False}))
    return {"status":status,"session":day}
