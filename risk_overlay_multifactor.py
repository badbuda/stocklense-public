from __future__ import annotations
import json, math
from pathlib import Path
from datetime import date
import pandas as pd
import yfinance as yf
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned

OUT=Path("research/risk_overlay_multifactor.json")
TICKERS=["^VIX","^VIX3M","^VVIX","^SKEW","HYG","LQD","TLT","UUP","GLD","QQQ","QQQE","SPY","RSP"]

# PREDECLARED research rules. Thresholds are fixed before outcome evaluation.
RULES=(
 ("baseline",None,3.0),
 ("vix_stress","vix",2.0),
 ("vix_term_backwardation","term",2.0),
 ("credit_stress","credit",2.0),
 ("participation_deterioration","participation",2.0),
 ("options_tail_stress","options",2.0),
 ("cross_asset_stress","cross_asset",2.0),
 ("vol_of_vol_stress","vol_of_vol",2.0),
 ("momentum_deterioration","momentum",2.0),
 ("ensemble_2of8_cap2","ensemble2",2.0),
 ("ensemble_3of8_cap125","ensemble3",1.25),
)
SPLITS={
 "development":("2012-01-03","2017-12-29"),
 "validation":("2018-01-02","2022-12-30"),
 "holdout_observational":("2023-01-03","2099-12-31"),
}

def _download(start,end):
    raw=yf.download(TICKERS,start=start,end=end,auto_adjust=True,progress=False,group_by="column",threads=False)
    if raw.empty: raise RuntimeError("risk overlay market context download returned no rows")
    close=raw["Close"] if isinstance(raw.columns,pd.MultiIndex) else raw
    close.index=pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()

def _ret(s,n):
    return s/s.shift(n)-1.0

def _features(close):
    x=pd.DataFrame(index=close.index)
    def col(t): return pd.to_numeric(close[t],errors="coerce") if t in close else pd.Series(index=close.index,dtype=float)
    vix=col("^VIX"); vix3=col("^VIX3M"); vvix=col("^VVIX"); skew=col("^SKEW")
    hyg,lqd,tlt,uup=col("HYG"),col("LQD"),col("TLT"),col("UUP")
    qqq,qqqe,spy,rsp=col("QQQ"),col("QQQE"),col("SPY"),col("RSP")
    # All features are observed on the PRIOR completed session; execution happens next session.
    x["vix"]=(vix>=30.0) | (_ret(vix,5)>=0.35)
    x["term"]=(vix/vix3>=1.0) & (vix>=20.0)
    x["credit"]=(_ret(hyg/lqd,20)<=-0.02) | (_ret(hyg,20)<=-0.05)
    # Tradable historical participation proxies; NOT constituent-level Nasdaq breadth.
    x["participation"]=(_ret(qqqe/qqq,63)<=-0.06) | (_ret(rsp/spy,63)<=-0.05)
    x["options"]=(skew>=150.0) & ((_ret(vix,5)>=0.15) | (vix>=25.0))
    x["cross_asset"]=(_ret(tlt,20)<=-0.06) & (_ret(uup,20)>=0.02)
    x["vol_of_vol"]=(vvix>=130.0) & (vix>=20.0)
    x["momentum"]=(_ret(qqq,63)<=-0.10) & (qqq/qqq.rolling(200).mean()<=0.95)
    core=x[["vix","term","credit","participation","options","cross_asset","vol_of_vol","momentum"]].fillna(False)
    x["stress_count"]=core.astype(int).sum(axis=1)
    x["ensemble2"]=x["stress_count"]>=2
    x["ensemble3"]=x["stress_count"]>=3
    return x

def _run(rows,tq,features,key,cap,cost_bps=5):
    nav=peak=100000.0; dd=0.0; costs=0.0; hits=0; prev=(0.0,0.0); rets=[]
    dates=[]; navs=[]
    for i in range(1,len(rows)):
        src=rows[i-1]; dt=pd.Timestamp(src["date"])
        exp=float(src["leverage"])
        active=False if key is None or dt not in features.index else bool(features.at[dt,key])
        if active and exp>cap: exp=cap; hits+=1
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.0,0.0)
        q=q0*TARGET_INVESTED_FRACTION; t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0
        tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.0
        before=nav; nav*=1.0+q*qr+t*tr
        fee=nav*(abs(q-prev[0])+abs(t-prev[1]))*cost_bps/10000.0
        nav-=fee; costs+=fee; peak=max(peak,nav); dd=min(dd,nav/peak-1.0)
        rets.append(nav/before-1.0); dates.append(rows[i]["date"]); navs.append(nav); prev=(q,t)
    years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.2425
    cagr=(nav/100000.0)**(1.0/years)-1.0 if years>0 and nav>0 else None
    return {"end_equity":nav,"cagr":cagr,"max_drawdown":dd,"intervention_sessions":hits,
            "estimated_turnover_cost":costs,"sessions":len(rets)}

def _score(item,base):
    # Descriptive Pareto diagnostic only; never promotion logic.
    return {"cagr_delta":item["cagr"]-base["cagr"],
            "maxdd_improvement":item["max_drawdown"]-base["max_drawdown"],
            "pareto_improves_both":item["cagr"]>=base["cagr"] and item["max_drawdown"]>=base["max_drawdown"]}

def build(out=OUT):
    rows,tq,_,_=_aligned()
    start=min(r["date"] for r in rows); end=(pd.Timestamp(max(r["date"] for r in rows))+pd.Timedelta(days=2)).date().isoformat()
    close=_download(start,end); f=_features(close)
    availability={t:{"first":(str(close[t].dropna().index.min().date()) if t in close and not close[t].dropna().empty else None),
                     "last":(str(close[t].dropna().index.max().date()) if t in close and not close[t].dropna().empty else None),
                     "observations":(int(close[t].notna().sum()) if t in close else 0)} for t in TICKERS}
    results=[{"name":n,"signal":k,"cap":cap,**_run(rows,tq,f,k,cap)} for n,k,cap in RULES]
    base=results[0]
    for x in results: x["vs_baseline"]=_score(x,base)
    split_results={}
    for label,(a,b) in SPLITS.items():
        rr=[r for r in rows if a<=r["date"]<=b]
        if len(rr)<252: continue
        vals=[{"name":n,"signal":k,"cap":cap,**_run(rr,tq,f,k,cap)} for n,k,cap in RULES]
        bb=vals[0]
        for x in vals: x["vs_baseline"]=_score(x,bb)
        split_results[label]=vals
    # Explicitly block fake constituent breadth: no current-constituent backfill is permitted.
    breadth={"status":"PROXY_ONLY","method":"historical ETF participation proxies (QQQE/QQQ and RSP/SPY)",
             "constituent_level_nasdaq_breadth":False,
             "blocker":"survivorship-safe point-in-time Nasdaq constituent history is not available in the current data contract",
             "forbidden":"backfilling today's Nasdaq constituents into historical breadth"}
    result={"schema_version":1,"status":"PASS","kind":"MULTIFACTOR_RISK_OVERLAY_RESEARCH_ONLY",
      "frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,
      "execution_semantics":"Every overlay reads only the prior completed session and can cap, never increase, frozen exposure for the next session.",
      "predeclared_rules":[{"name":n,"signal":k,"cap":cap} for n,k,cap in RULES],
      "feature_definitions":{
        "vix":"VIX>=30 OR 5-session VIX change>=35%",
        "term":"VIX/VIX3M>=1 AND VIX>=20",
        "credit":"20-session HYG/LQD<=-2% OR HYG<=-5%",
        "participation":"63-session QQQE/QQQ<=-6% OR RSP/SPY<=-5%; ETF proxy only",
        "options":"SKEW>=150 AND (5-session VIX change>=15% OR VIX>=25)",
        "cross_asset":"20-session TLT<=-6% AND UUP>=+2%",
        "vol_of_vol":"VVIX>=130 AND VIX>=20",
        "momentum":"63-session QQQ<=-10% AND QQQ<=95% of SMA200",
        "ensemble2":"at least 2 of 8 declared stress families",
        "ensemble3":"at least 3 of 8 declared stress families"},
      "data_availability":availability,"breadth_contract":breadth,"results":results,
      "time_splits":SPLITS,"split_results":split_results,
      "claim_boundary":"Exploratory predeclared risk-overlay comparison. Historical thresholds are not pristine prospective evidence. PASS means the package executed with declared semantics, not that an overlay is validated or investable.",
      "selection_policy":"NONE_NO_AUTOMATIC_WINNER_NO_RETUNING"}
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(result,indent=2)+"\n")
    return result

if __name__=="__main__": print(json.dumps(build(),indent=2))
