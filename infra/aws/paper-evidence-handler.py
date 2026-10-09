import boto3,hashlib,json,os,urllib.request
from botocore.exceptions import ClientError
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
ROOT="https://raw.githubusercontent.com/badbuda/stocklense-public/main/"
def read(path):
    req=urllib.request.Request(ROOT+path,headers={"User-Agent":"StockLens/1"})
    with urllib.request.urlopen(req,timeout=12) as r: b=r.read(200001)
    if len(b)>200000: raise ValueError("TOO_LARGE")
    return b
def evidence(now,rep,snap,prior,cur):
    ny=now.astimezone(ZoneInfo("America/New_York"))
    day=str(ny.date()-timedelta(days=1))
    if ny.weekday() in (0,6) or not 4<=ny.hour<18: raise RuntimeError("NOT_CLOSED")
    if rep.get("status")!="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS" or rep.get("latest_session")!=day or rep.get("broker_fills_observed") is not False:
        raise RuntimeError("AUDIT_NOT_PASS")
    if cur.get("latest",{}).get("asof_date")!=day or cur.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("NO_LATEST_SIGNAL")
    if snap.get("schema_version")!=1 or snap.get("session_date")!=day or snap.get("broker_fills_observed") is not False:
        raise RuntimeError("INVALID_SESSION_RECEIPT")
    row=snap.get("row",{})
    mt=snap.get("trades",[])
    if row.get("session_date")!=day or type(mt)!=list:
        raise RuntimeError("BAD_RECEIPT")
    if row.get("execution_source")!="YFINANCE_1M_RAW": raise RuntimeError("SYNTHETIC_SOURCE")
    sig=row.get("signal_date","")
    if not sig or sig>=day or prior.get("latest",{}).get("asof_date")!=sig or prior.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("BAD_PRIOR_SIGNAL")
    at=datetime.fromisoformat(prior["generated_at_utc"].replace("Z","+00:00"))
    op=datetime.fromisoformat(day+"T09:30:00").replace(tzinfo=ZoneInfo("America/New_York"))
    if not at.tzinfo or at>=op: raise RuntimeError("LATE_SIGNAL")
    for k in ("qqq_weight","tqqq_weight"):
        if abs(float(prior["latest"][k])-float(row["target_"+k]))>1e-9:
            raise RuntimeError("WRONG_TARGET")
    if len(mt)!=int(row["trade_count_session"]): raise RuntimeError("TRADE_COUNT_BAD")
    for t in mt:
        if t.get("symbol") not in ("QQQ","TQQQ") or t.get("side") not in ("BUY","SELL"):
            raise RuntimeError("BAD_SYMBOL")
        if t.get("signal_date")!=sig or t.get("execution_session")!=day or t.get("time_et")!=("09:31" if t["side"]=="SELL" else "09:32"):
            raise RuntimeError("BAD_TRADE_WINDOW")
    return day,row,mt
def handler(event,context):
    now=datetime.now(timezone.utc)
    rep=json.loads(read("docs/paper_portfolio_integrity.json"))
    snap=json.loads(read("paper_portfolio/latest_session.json"))
    cur=json.loads(read("shadow_history/latest.json"))
    sig=snap.get("row",{}).get("signal_date","")
    if len(sig)!=10 or not sig.replace("-","").isdigit() or sig.count("-")!=2:
        raise RuntimeError("BAD_SIGNAL_PATH")
    prior=json.loads(read("shadow_history/"+sig+".json"))
    day,row,mt=evidence(now,rep,snap,prior,cur)
    pay=json.dumps({"row":row,"trs":mt},sort_keys=True,separators=(",",":"))
    item={"session_date":{"S":day+"#PAPER"},"paper_evidence_json":{"S":pay},
          "paper_sha256":{"S":hashlib.sha256(pay.encode()).hexdigest()},
          "broker_orders_authorized":{"BOOL":False},"broker_fills_observed":{"BOOL":False}}
    try:
        boto3.client("dynamodb").put_item(TableName=os.environ["TABLE_NAME"],
            Item=item,ConditionExpression="attribute_not_exists(session_date)",
            ReturnValuesOnConditionCheckFailure="ALL_OLD")
        status="ARCHIVED"
    except ClientError as exc:
        if exc.response.get("Error",{}).get("Code")!="ConditionalCheckFailedException": raise
        old=exc.response.get("Item") or {}
        if old.get("paper_sha256",{}).get("S")!=item["paper_sha256"]["S"]:
            raise RuntimeError("DIVERGENT_PAPER_DUPLICATE") from exc
        status="MATCHED_DUPLICATE"
    print(json.dumps({"status":status,"session":day,"actual_broker_fills":False}))
    return {"status":status,"session":day}
