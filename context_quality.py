from __future__ import annotations
import csv,json
from datetime import date
from pathlib import Path
from json_artifacts import write_json_atomic
def build(out="shadow_history/context_quality.json"):
    p=Path("shadow_history/market_context.json");c=json.loads(p.read_text()) if p.exists() else {}
    v=c.get("vix") or {};asof=c.get("asof_date");fresh=None
    if asof:
        try:fresh=(date.today()-date.fromisoformat(asof)).days<=4
        except:fresh=False
    hp=Path("shadow_history/market_context_history.csv");rows=list(csv.DictReader(hp.open())) if hp.exists() else []
    r={"status":"AVAILABLE" if v.get("status")=="AVAILABLE" else "DEGRADED","vix_available":v.get("status")=="AVAILABLE","vix_fresh_calendar_days":fresh,"history_sessions":len(rows),"affects_frozen_signal":False,"blocking":False,"interpretation":"Research context only; quality never gates StockLens 8.0 signal generation."}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
