from __future__ import annotations
import csv,hashlib,json
from pathlib import Path
import pandas as pd
from stocklens.data import load_qqq_history
from stocklens.core import replay_levels

SCHEMA_VERSION=1

def _sha(rows):
    payload="\n".join(",".join(str(r[k]) for k in ("date","close","qqq_return","baseline_leverage")) for r in rows)
    return hashlib.sha256(payload.encode()).hexdigest()

def build_baseline_dataset(csv_path=None,out="research/data/stocklens8_daily.csv"):
    df,audit=load_qqq_history(csv_path=csv_path)
    dates=df["Date"].dt.date.astype(str).tolist();closes=df["Close"].astype(float).tolist()
    decisions={d.asof_date:d for d in replay_levels(closes,dates)}
    rows=[]
    for i in range(1,len(df)):
        date=dates[i];prev=dates[i-1]
        if prev not in decisions:continue
        qret=closes[i]/closes[i-1]-1.0
        # Decision at prior completed close is applied only to the next session return.
        lev=float(decisions[prev].target_leverage)
        rows.append({"date":date,"close":closes[i],"qqq_return":qret,"baseline_leverage":lev,
                     "baseline_return":qret*lev})
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    manifest={"schema_version":SCHEMA_VERSION,"kind":"RESEARCH_DATASET_NOT_QC_PARITY",
              "source_audit":audit,"rows":len(rows),"first_date":rows[0]["date"],
              "last_date":rows[-1]["date"],"sha256":_sha(rows),
              "timing":"prior completed-session signal applied to next-session close-to-close return",
              "limitations":["Yahoo adjusted QQQ is research data, not identical QuantConnect/LEAN input evidence",
                             "leveraged return is a research approximation and does not model TQQQ path, fees, slippage or intraday execution"]}
    Path(str(p)+".manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest

if __name__=="__main__":print(json.dumps(build_baseline_dataset(),indent=2))
