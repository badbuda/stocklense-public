from __future__ import annotations
import csv,json
from datetime import datetime,timezone
from pathlib import Path
from json_artifacts import write_json_atomic
def _rows(p):
 q=Path(p);return list(csv.DictReader(q.open())) if q.exists() else []
def _num(v,default=None):
 try:return float(v) if v not in (None,"") else default
 except (TypeError,ValueError):return default
def build(out="docs/timeseries.json"):
 hist=_rows("historical_replay/daily_states.csv");paper=_rows("paper_portfolio/ledger.csv");ctx=_rows("shadow_history/market_context_history.csv")
 vix={r["asof_date"]:_num(r.get("vix")) for r in ctx if r.get("asof_date") and _num(r.get("vix")) is not None}
 series=[{"date":r.get("asof_date"),"level":int(_num(r.get("level"),0)),"defense":str(r.get("defense_active","")).lower()=="true","leverage":_num(r.get("target_leverage"),0),"qqq":_num(r.get("close")),"vol20":_num(r.get("vol20")),"mom12":_num(r.get("mom12")),"sma50":_num(r.get("sma50")),"sma200":_num(r.get("sma200")),"vix":vix.get(r.get("asof_date"))} for r in hist]
 pp=[];start_equity=_num(paper[0].get("equity")) if paper else None;start_qqq=_num(paper[0].get("qqq_close")) if paper else None
 for r in paper:
  equity=_num(r.get("equity"));qqq=_num(r.get("qqq_close"))
  stock_ret=(equity/start_equity-1) if start_equity and equity is not None else None
  qqq_ret=(qqq/start_qqq-1) if start_qqq and qqq is not None else None
  pp.append({"date":r.get("session_date"),"stocklens_nav":equity,"qqq_nav":start_equity*(1+qqq_ret) if start_equity and qqq_ret is not None else None,
   "stocklens_return":stock_ret,"qqq_return":qqq_ret,"excess_return":stock_ret-qqq_ret if stock_ret is not None and qqq_ret is not None else None,
   "drawdown":_num(r.get("drawdown")),"qqq_close":qqq})
 latest=pp[-1] if pp else {}
 def _maxdd(vals):
  peak=None;dd=0.0
  for v in vals:
   if v is None: continue
   peak=v if peak is None else max(peak,v);dd=min(dd,v/peak-1 if peak else 0)
  return dd
 sessions=max(0,len(pp)-1)
 slret=latest.get("stocklens_return");qret=latest.get("qqq_return")
 slann=(1+slret)**(252/sessions)-1 if sessions>=20 and slret is not None and slret>-1 else None
 qann=(1+qret)**(252/sessions)-1 if sessions>=20 and qret is not None and qret>-1 else None
 result={"schema_version":2,"historical":series,"paper":pp,
  "comparison":{"status":"ACTIVE" if len(pp)>=2 else "WAITING_FOR_PROSPECTIVE_DATA","start_equity":start_equity,
   "stocklens_return":slret,"qqq_return":qret,"excess_return":latest.get("excess_return"),
   "stocklens_nav":latest.get("stocklens_nav"),"qqq_nav":latest.get("qqq_nav"),"sessions":len(pp),
   "stocklens_profit":latest.get("stocklens_nav")-start_equity if latest.get("stocklens_nav") is not None and start_equity else None,
   "qqq_profit":latest.get("qqq_nav")-start_equity if latest.get("qqq_nav") is not None and start_equity else None,
   "profit_advantage":latest.get("stocklens_nav")-latest.get("qqq_nav") if latest.get("stocklens_nav") is not None and latest.get("qqq_nav") is not None else None,
   "stocklens_annualized_return":slann,"qqq_annualized_return":qann,
   "stocklens_max_drawdown":_maxdd([x.get("stocklens_nav") for x in pp]),"qqq_max_drawdown":_maxdd([x.get("qqq_nav") for x in pp])},
  "available_range":{"start":series[0]["date"] if series else None,"end":series[-1]["date"] if series else None},
  "last_updated_session":pp[-1]["date"] if pp else (series[-1]["date"] if series else None),
  "generated_at_utc":datetime.now(timezone.utc).isoformat(),
  "note":"Prospective StockLens paper and QQQ benchmark are normalized to the same starting capital; historical replay remains a separate evidence class."}
 write_json_atomic(out,result);return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
