from __future__ import annotations
import csv,json
from datetime import datetime,timezone
from pathlib import Path
from json_artifacts import write_json_atomic
SCHEMA_VERSION=2
def _regime(v):
    if v is None:return "UNAVAILABLE"
    if v<15:return "LOW"
    if v<25:return "NORMAL"
    if v<35:return "ELEVATED"
    return "HIGH"
def build_market_context(out_path="shadow_history/market_context.json",history_path="shadow_history/market_context_history.csv"):
    vix=None;asof=None;status="UNAVAILABLE";err=None
    try:
        import yfinance as yf
        d=yf.download("^VIX",period="10d",interval="1d",auto_adjust=False,progress=False,threads=False)
        if not d.empty:
            s=d["Close"].dropna()
            if hasattr(s,"columns"):s=s.iloc[:,0]
            if len(s):
                vix=float(s.iloc[-1]);asof=str(s.index[-1].date());status="AVAILABLE"
    except Exception as e:err=type(e).__name__
    result={"schema_version":SCHEMA_VERSION,"mode":"OBSERVATIONAL_ONLY","affects_frozen_signal":False,"asof_date":asof,
      "vix":{"value":vix,"regime":_regime(vix),"source":"Yahoo Finance ^VIX","status":status},
      "fear_greed":None,"generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "notes":["Context is observational only.","Missing context never changes or blocks StockLens 8.0.","Any future decision use requires a separately versioned validated model."]}
    if err:result["vix"]["error_type"]=err
    write_json_atomic(out_path,result)
    hp=Path(history_path);hp.parent.mkdir(parents=True,exist_ok=True)
    existing=[]
    if hp.exists():
        with hp.open(newline="") as f:existing=list(csv.DictReader(f))
    if asof and not any(r.get("asof_date")==asof for r in existing):
        with hp.open("a",newline="") as f:
            w=csv.DictWriter(f,fieldnames=["asof_date","vix","regime","source"]); 
            if not existing:w.writeheader()
            w.writerow({"asof_date":asof,"vix":vix,"regime":_regime(vix),"source":"Yahoo Finance ^VIX"})
    return result
if __name__=="__main__":print(json.dumps(build_market_context(),indent=2))
