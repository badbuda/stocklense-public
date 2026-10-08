from __future__ import annotations
import csv,json
from pathlib import Path
from json_artifacts import write_json_atomic
from research_factor_coverage import factor_coverage
def build(out="docs/research.json"):
    p=Path("historical_replay/daily_states.csv");rows=list(csv.DictReader(p.open())) if p.exists() else []
    cp=Path("shadow_history/market_context_history.csv");ctx=list(csv.DictReader(cp.open())) if cp.exists() else []
    vix={x["asof_date"]:float(x["vix"]) for x in ctx if x.get("asof_date") and x.get("vix")}
    data=[{"date":r.get("asof_date"),"close":float(r.get("close",0)),"sma50":float(r.get("sma50",0)),"sma200":float(r.get("sma200",0)),"vol20":float(r.get("vol20",0)),"mom12":float(r.get("mom12",0)),"frozen_level":int(r.get("level",0)),"frozen_defense":str(r.get("defense_active","")).lower()=="true","frozen_leverage":float(r.get("target_leverage",0)),"vix":vix.get(r.get("asof_date"))} for r in rows]
    r={"schema_version":2,"mode":"RESEARCH_SANDBOX","vix_coverage_sessions":sum(x["vix"] is not None for x in data),"vix_coverage_start":next((x["date"] for x in data if x["vix"] is not None),None),"factor_coverage":{"vix":factor_coverage(data,"vix")},"baseline":"StockLens 8.0 FROZEN","rows":data,"controls":{"trend_retention_floor":{"baseline":0.99,"min":0.95,"max":1.02,"step":0.005},"trend_reentry":{"baseline":1.01,"min":0.98,"max":1.05,"step":0.005},"l3_to_l2_vol":{"baseline":0.32,"min":0.20,"max":0.50,"step":0.01},"l2_to_l3_vol":{"baseline":0.28,"min":0.15,"max":0.40,"step":0.01},"l2_to_l1_vol":{"baseline":0.42,"min":0.25,"max":0.65,"step":0.01},"l1_to_l3_vol":{"baseline":0.28,"min":0.15,"max":0.40,"step":0.01},"l1_to_l2_vol":{"baseline":0.38,"min":0.20,"max":0.55,"step":0.01},"vix_filter":{"baseline":None,"options":[None,20,25,30,35,40]}},"warning":"Sandbox only. Results cannot modify frozen 8.0 without separate validation and versioning."}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
