import boto3,csv,hashlib,io,json,os,urllib.request
from botocore.exceptions import ClientError
from datetime import datetime,time,timezone
from zoneinfo import ZoneInfo
ROOT="https://raw.githubusercontent.com/badbuda/stocklense-public/main/"
def read(path):
    req=urllib.request.Request(ROOT+path,headers={"User-Agent":"StockLens/1"})
    with urllib.request.urlopen(req,timeout=12) as r: b=r.read(200001)
    if len(b)>200000: raise ValueError("TOO_LARGE")
    return b
def evidence(now,rep,lg,trs,prior,cur):
    ny=now.astimezone(ZoneInfo("America/New_York"))
    day=ny.date().isoformat()
    if ny.weekday()>4 or ny.time()<time(18,0):
        raise RuntimeError("NOT_CLOSED")
    if rep.get("status")!="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS":
        raise RuntimeError("AUDIT_NOT_PASS")
    if rep.get("latest_session")!=day or rep.get("broker_fills_observed") is not False:
        raise RuntimeError("NO_PROSPECTIVE_PAPER")
    if cur.get("latest",{}).get("asof_date")!=day or cur.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("NO_LATEST_SIGNAL")
    rows=list(csv.DictReader(io.StringIO(lg)))
    if not rows or rows[-1].get("session_date")!=day or sum(r["session_date"]==day for r in rows)!=1:
        raise RuntimeError("BAD_LEDGER")
    row=rows[-1]
    if row.get("execution_source")!="YFINANCE_1M_RAW":
        raise RuntimeError("SYNTHETIC_SOURCE")
    sig=row.get("signal_date","")
    if sig>=day or prior.get("latest",{}).get("asof_date")!=sig or prior.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("BAD_PRIOR_SIGNAL")
    at=datetime.fromisoformat(prior["generated_at_utc"].replace("Z","+00:00"))
    op=datetime.fromisoformat(day+"T09:30:00").replace(tzinfo=ZoneInfo("America/New_York"))
    if at.tzinfo is None or at>=op:
        raise RuntimeError("LATE_SIGNAL")
    for k in ("qqq_weight","tqqq_weight"):
        if abs(float(prior["latest"][k])-float(row["target_"+k]))>1e-9:
            raise RuntimeError("WRONG_TARGET")
    mt=[t for t in csv.DictReader(io.StringIO(trs)) if t.get("execution_session")==day]
    if len(mt)!=int(row["trade_count_session"]):
        raise RuntimeError("TRADE_COUNT_BAD")
    for t in mt:
        if t.get("symbol") not in ("QQQ","TQQQ") or t.get("side") not in ("BUY","SELL"):
            raise RuntimeError("BAD_SYMBOL")
        if t.get("signal_date")!=sig or t.get("time_et")!=("09:31" if t["side"]=="SELL" else "09:32"):
            raise RuntimeError("BAD_TRADE_WINDOW")
    return day,row,mt
def handler(event,context):
    now=datetime.now(timezone.utc)
    rep=json.loads(read("docs/paper_portfolio_integrity.json"))
    lg=read("paper_portfolio/lg.csv").decode()
    trs=read("paper_portfolio/trs.csv").decode()
    cur=json.loads(read("shadow_history/latest.json"))
    rows=list(csv.DictReader(io.StringIO(lg)))
    if not rows: raise RuntimeError("NO_PAPER_SESSION")
    prior=json.loads(read("shadow_history/"+rows[-1]["signal_date"]+".json"))
    day,row,mt=evidence(now,rep,lg,trs,prior,cur)
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
