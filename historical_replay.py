from __future__ import annotations
import csv, hashlib, json
from datetime import date, timedelta
from pathlib import Path
from stocklens.core import replay_levels
from stocklens.data import load_qqq_history

FIELDS=["asof_date","level","defense_active","target_leverage","qqq_weight","tqqq_weight","invested_fraction","close","sma50","sma200","vol20","mom12","action"]

def build_historical_replay(days=365,out_dir="historical_replay"):
    df,audit=load_qqq_history()
    dates=[d.date().isoformat() for d in df["Date"]]; closes=[float(x) for x in df["Close"]]
    decisions=replay_levels(closes,dates)
    cutoff=df["Date"].iloc[-1].date()-timedelta(days=days)
    selected=[d for d in decisions if date.fromisoformat(d.asof_date)>=cutoff]
    rows=[]; prev=None
    for d in selected:
        action="NO_CHANGE"
        if prev and (prev.target_leverage!=d.target_leverage or prev.defense_active!=d.defense_active):
            action="ENTER_CASH_NEXT_SESSION" if d.defense_active else ("EXIT_CASH_NEXT_SESSION" if prev.defense_active else "REBALANCE_NEXT_SESSION")
        f=d.features
        rows.append({"asof_date":d.asof_date,"level":d.level,"defense_active":d.defense_active,"target_leverage":d.target_leverage,"qqq_weight":d.qqq_weight,"tqqq_weight":d.tqqq_weight,"invested_fraction":d.invested_fraction,"close":f.close,"sma50":f.sma50,"sma200":f.sma200,"vol20":f.vol20,"mom12":f.mom12,"action":action})
        prev=d
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True); csvp=out/"daily_states.csv"
    with csvp.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    digest=hashlib.sha256(csvp.read_bytes()).hexdigest()
    summary={"kind":"HISTORICAL_REPLAY_NOT_PROSPECTIVE","frozen_model":"StockLens 8.0","sessions":len(rows),"first_date":rows[0]["asof_date"] if rows else None,"last_date":rows[-1]["asof_date"] if rows else None,"state_transitions":sum(1 for r in rows if r["action"]!="NO_CHANGE"),"defense_sessions":sum(bool(r["defense_active"]) for r in rows),"level_counts":{str(k):sum(r["level"]==k for r in rows) for k in (1,2,3)},"dataset_sha256":digest,"source_audit":audit}
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary
if __name__=="__main__":print(json.dumps(build_historical_replay(),indent=2))
