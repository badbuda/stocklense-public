from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from datetime import date
from risk_overlay_multifactor import _download,_features,_run,_score,TICKERS
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned

OUT=Path("research/risk_overlay_deep_dive.json")
# Frozen before outcome evaluation. These are mechanism tests, not a parameter optimizer.
VARIANTS=(
 ("baseline",None,3.0),
 ("term_cap2","term",2.0),
 ("term_severe_cap125","term_severe",1.25),
 ("term_severe_pulse3_cap2","term_severe_pulse3",2.0),
 ("term_severe_pulse5_cap2","term_severe_pulse5",2.0),
 ("term_severe_pulse5_or_momentum_break_cap2","term_severe_pulse5_or_momentum_break",2.0),
 ("term_severe_pulse5_or_trend_break_cap2","term_severe_pulse5_or_trend_break",2.0),
 ("term_severe_pulse5_or_credit_momentum_cap2","term_severe_pulse5_or_credit_momentum",2.0),
 ("realized_vol30_cap2","realized_vol30",2.0),
 ("qqq_drawdown10_cap2","qqq_drawdown10",2.0),
 ("qqq_drawdown15_cap125","qqq_drawdown15",1.25),
 ("fast_shock5d7_pulse5_cap2","fast_shock5d7_pulse5",2.0),
 ("trend200_negative20_cap2","trend200_negative20",2.0),
 ("market_credit_joint_cap2","market_credit_joint",2.0),
 ("pulse5_or_drawdown10_cap2","pulse5_or_drawdown10",2.0),
 ("term_severe_pulse10_cap2","term_severe_pulse10",2.0),
 ("term_severe_pulse3_cap125","term_severe_pulse3",1.25),
 ("term_severe_pulse5_cap125","term_severe_pulse5",1.25),
 ("term_severe_pulse10_cap125","term_severe_pulse10",1.25),
 ("term_severe_recovery3_cap125","term_severe_recovery3",1.25),
 ("term_persist2_cap2","term_persist2",2.0),
 ("term_or_cross_cap2","term_or_cross",2.0),
 ("term_and_cross_cap125","term_and_cross",1.25),
 ("term_or_vvix_cap2","term_or_vvix",2.0),
 ("term_or_participation_cap2","term_or_participation",2.0),
 ("term_cross_confirmed_cap2","term_cross_confirmed",2.0),
 ("term_hysteresis3_cap2","term_hysteresis3",2.0),
 ("term_recovery_confirmed_cap2","term_recovery_confirmed",2.0),
 ("credit_term_cap2","credit_term",2.0),
 ("breadth_term_cap2","breadth_term",2.0),
)
COSTS=(5,25,50,100)
LAGS=(0,1,2,5)
MAJOR_DD_STARTS=("2010-04-01","2011-04-01","2015-04-01","2018-08-01","2020-01-01","2021-10-01","2024-06-01")

def _recovery_state(stress,recovery,confirm_sessions=3):
    """Causal state machine: enter on stress; exit only after N consecutive completed recovery sessions."""
    active=False; streak=0; vals=[]
    for s,r in zip(stress.fillna(False).astype(bool),recovery.fillna(False).astype(bool)):
        if s:
            active=True; streak=0
        elif active:
            streak=streak+1 if r else 0
            if streak>=confirm_sessions: active=False; streak=0
        vals.append(active)
    return pd.Series(vals,index=stress.index,dtype=bool)

def _fixed_pulse(stress,sessions):
    """Causal fixed-duration pulse from each observed stress session; current/past only."""
    return stress.fillna(False).astype(bool).rolling(sessions,min_periods=1).max().astype(bool)

def _augment(close):
    f=_features(close)
    vix=pd.to_numeric(close["^VIX"],errors="coerce"); v3=pd.to_numeric(close["^VIX3M"],errors="coerce")
    ratio=vix/v3
    f["term_ratio"]=ratio
    f["term_severe"]=(ratio>=1.08)&(vix>=25)
    f["term_severe_pulse3"]=_fixed_pulse(f["term_severe"],3)
    f["term_severe_pulse5"]=_fixed_pulse(f["term_severe"],5)
    f["term_severe_pulse10"]=_fixed_pulse(f["term_severe"],10)
    qqq=pd.to_numeric(close["QQQ"],errors="coerce")
    # Complementary slow-burn families: fixed, causal market-damage conditions rather than more volatility-curve tuning.
    f["momentum_break"]=((qqq/qqq.shift(63)-1)<=-0.10) & (qqq/qqq.rolling(200).mean()<=0.95)
    f["trend_break"]=(qqq/qqq.rolling(200).mean()<=0.90)
    f["credit_momentum"]=f["credit"] & ((qqq/qqq.shift(63)-1)<=-0.08)
    f["term_severe_pulse5_or_momentum_break"]=f["term_severe_pulse5"]|f["momentum_break"]
    f["term_severe_pulse5_or_trend_break"]=f["term_severe_pulse5"]|f["trend_break"]
    f["term_severe_pulse5_or_credit_momentum"]=f["term_severe_pulse5"]|f["credit_momentum"]
    # Independent predeclared mechanism families. Round thresholds are fixed before outcome inspection.
    qret=qqq.pct_change()
    f["rv20"]=qret.rolling(20).std()*(252**0.5)
    f["realized_vol30"]=(f["rv20"]>=0.30)
    prior_high=qqq.rolling(252,min_periods=126).max()
    qdd=qqq/prior_high-1.0
    f["qdd252"]=qdd
    f["qqq_drawdown10"]=(qdd<=-0.10)
    f["qqq_drawdown15"]=(qdd<=-0.15)
    f["fast_shock5d7_pulse5"]=_fixed_pulse((qqq/qqq.shift(5)-1.0)<=-0.07,5)
    f["trend200_negative20"]=(qqq<=qqq.rolling(200).mean()) & ((qqq/qqq.shift(20)-1.0)<0)
    spy=pd.to_numeric(close["SPY"],errors="coerce"); hyg=pd.to_numeric(close["HYG"],errors="coerce"); lqd=pd.to_numeric(close["LQD"],errors="coerce")
    f["market_credit_joint"]=((spy/spy.shift(20)-1.0)<=-0.05) & (((hyg/lqd)/(hyg/lqd).shift(20)-1.0)<=-0.02)
    f["pulse5_or_drawdown10"]=f["term_severe_pulse5"]|f["qqq_drawdown10"]
    recovery=(vix<20)&(ratio<0.95)
    f["term_severe_recovery3"]=_recovery_state(f["term_severe"],recovery,3)
    f["term_persist2"]=f["term"].rolling(2,min_periods=2).sum()>=2
    f["term_or_cross"]=f["term"]|f["cross_asset"]
    f["term_and_cross"]=f["term"]&f["cross_asset"]
    f["term_or_vvix"]=f["term"]|f["vol_of_vol"]
    f["term_or_participation"]=f["term"]|f["participation"]
    f["term_cross_confirmed"]=f["term"]&(f["cross_asset"]|f["participation"]|f["credit"])
    # Fixed recovery hysteresis: remain defensive for 3 completed sessions after acute term stress clears.
    f["term_hysteresis3"]=f["term"].rolling(4,min_periods=1).max().astype(bool)
    f["term_recovery_confirmed"]=f["term_hysteresis3"] & ~((vix<20)&(ratio<0.95))
    f["credit_term"]=f["term"]|((f["credit"])&(vix>=22))
    f["breadth_term"]=f["term"]|(f["participation"]&(vix>=22))
    return f

def _dynamic_cap_run(rows,tq,features,mode,cost_bps=5):
    """Research-only causal leverage schedule. Reads prior completed-session features and can only reduce frozen exposure."""
    nav=peak=100000.0; dd=0.0; costs=0.0; hits=0; prev=(0.0,0.0)
    for i in range(1,len(rows)):
        src=rows[i-1]; dt=pd.Timestamp(src["date"]); frozen=float(src["leverage"]); cap=3.0
        if dt in features.index:
            rv=float(features.at[dt,"rv20"]) if pd.notna(features.at[dt,"rv20"]) else 0.0
            qdd=float(features.at[dt,"qdd252"]) if pd.notna(features.at[dt,"qdd252"]) else 0.0
            trend=bool(features.at[dt,"trend200_negative20"])
            pulse=bool(features.at[dt,"term_severe_pulse5"])
            if mode=="vol_target": cap=max(1.0,min(3.0,0.60/max(rv,0.01)))
            elif mode=="vol_tiers": cap=1.5 if rv>=0.40 else (2.0 if rv>=0.30 else (2.5 if rv>=0.22 else 3.0))
            elif mode=="dd_budget": cap=1.25 if qdd<=-0.15 else (2.0 if qdd<=-0.10 else (2.5 if qdd<=-0.05 else 3.0))
            elif mode=="trend_vol": cap=min(2.0 if trend else 3.0, 1.5 if rv>=0.40 else (2.0 if rv>=0.30 else (2.5 if rv>=0.22 else 3.0)))
            elif mode=="pulse_vol": cap=min(2.0 if pulse else 3.0, max(1.0,min(3.0,0.60/max(rv,0.01))))
            elif mode=="pulse_dd": cap=min(2.0 if pulse else 3.0, 1.25 if qdd<=-0.15 else (2.0 if qdd<=-0.10 else (2.5 if qdd<=-0.05 else 3.0)))
            elif mode=="vol_high_only": cap=max(1.25,min(3.0,0.75/max(rv,0.01))) if rv>=0.25 else 3.0
            elif mode=="vol_tiers_light": cap=1.75 if rv>=0.40 else (2.25 if rv>=0.30 else (2.75 if rv>=0.25 else 3.0))
            elif mode=="pulse_vol_high_only": cap=min(2.0 if pulse else 3.0, max(1.25,min(3.0,0.75/max(rv,0.01))) if rv>=0.25 else 3.0)
            elif mode=="pulse_vol_tiers_light": cap=min(2.0 if pulse else 3.0, 1.75 if rv>=0.40 else (2.25 if rv>=0.30 else (2.75 if rv>=0.25 else 3.0)))
        exp=min(frozen,cap); hits+=int(exp<frozen-1e-12)
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.0,0.0); q=q0*TARGET_INVESTED_FRACTION; t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0; tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.0
        before=nav; nav*=1.0+q*qr+t*tr; fee=nav*(abs(q-prev[0])+abs(t-prev[1]))*cost_bps/10000.0; nav-=fee; costs+=fee
        peak=max(peak,nav); dd=min(dd,nav/peak-1.0); prev=(q,t)
    years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.2425
    return {"end_equity":nav,"cagr":(nav/100000.0)**(1.0/years)-1.0,"max_drawdown":dd,"intervention_sessions":hits,"estimated_turnover_cost":costs,"sessions":len(rows)-1}

DYNAMIC_MODES=("vol_target","vol_tiers","dd_budget","trend_vol","pulse_vol","pulse_dd","vol_high_only","vol_tiers_light","pulse_vol_high_only","pulse_vol_tiers_light")

def _lag_features(f,lag):
    if lag<=0:return f
    out=f.copy()
    boolcols=[c for c in out.columns if out[c].dtype==bool]
    out[boolcols]=out[boolcols].shift(lag).fillna(False).astype(bool)
    return out

def _episode_diagnostics(rows,f):
    idx=pd.to_datetime([r["date"] for r in rows]); lev=pd.Series([float(r["leverage"]) for r in rows],index=idx)
    out=[]
    for s in MAJOR_DD_STARTS:
        start=pd.Timestamp(s); end=start+pd.Timedelta(days=180)
        w=f.loc[(f.index>=start)&(f.index<=end)]
        if w.empty:continue
        active=w.index[w["term"].fillna(False)]
        cross=w.index[w["cross_asset"].fillna(False)]
        out.append({"window_start":s,"first_term_signal":str(active[0].date()) if len(active) else None,
                    "term_signal_days":int(w["term"].fillna(False).sum()),
                    "first_cross_asset_signal":str(cross[0].date()) if len(cross) else None,
                    "cross_asset_signal_days":int(w["cross_asset"].fillna(False).sum()),
                    "max_frozen_leverage":float(lev.loc[(lev.index>=start)&(lev.index<=end)].max()) if any((lev.index>=start)&(lev.index<=end)) else None})
    return out

def _signal_diagnostics(f):
    out={}
    for _,key,_ in VARIANTS[1:]:
        s=f[key].fillna(False).astype(bool)
        starts=s & ~s.shift(1,fill_value=False)
        out[key]={"active_sessions":int(s.sum()),"active_fraction":float(s.mean()),"episodes":int(starts.sum()),
                  "longest_active_run":int(s.groupby((s!=s.shift()).cumsum()).sum().max()) if len(s) else 0}
    return out

def _rolling_proxy(rows,tq,f,years=(1,3,5)):
    out={}
    for y in years:
        # Quarterly starts retain broad rolling coverage while keeping CI runtime bounded; this cadence is predeclared before outcome review.
        step=63; width=252*y; vals=[]
        for start in range(0,max(0,len(rows)-width),step):
            rr=rows[start:start+width+1]
            if len(rr)<width: continue
            b=_run(rr,tq,f,None,3.0,5)
            for name,key,cap in VARIANTS[1:]:
                r=_run(rr,tq,f,key,cap,5)
                vals.append({"name":name,"cagr_delta":r["cagr"]-b["cagr"],"maxdd_improvement":r["max_drawdown"]-b["max_drawdown"]})
        summary={}
        for name,_,_ in VARIANTS[1:]:
            xs=[x for x in vals if x["name"]==name]
            if xs: summary[name]={"windows":len(xs),"dd_improved_fraction":sum(x["maxdd_improvement"]>0 for x in xs)/len(xs),
                                  "median_cagr_delta":float(pd.Series([x["cagr_delta"] for x in xs]).median()),
                                  "median_maxdd_improvement":float(pd.Series([x["maxdd_improvement"] for x in xs]).median())}
        out[str(y)+"y"]=summary
    return out

def _false_alarm_cost(rows,tq,f):
    out={}
    qqq=pd.Series([float(r["close"]) for r in rows],index=pd.to_datetime([r["date"] for r in rows]))
    fwd20=qqq.shift(-20)/qqq-1.0
    for name,key,cap in VARIANTS[1:]:
        s=f[key].reindex(qqq.index).fillna(False).astype(bool)
        starts=s & ~s.shift(1,fill_value=False)
        dates=starts[starts].index
        vals=fwd20.reindex(dates).dropna()
        out[name]={"episodes_with_20d_outcome":int(len(vals)),
                   "false_alarm_fraction_qqq_up_20d":float((vals>0).mean()) if len(vals) else None,
                   "median_qqq_20d_after_signal":float(vals.median()) if len(vals) else None,
                   "severe_followthrough_fraction_qqq_down_10pct":float((vals<=-0.10).mean()) if len(vals) else None}
    return out

def _lead_time_diagnostics(rows,f):
    idx=pd.to_datetime([r["date"] for r in rows]); lev=pd.Series([float(r["leverage"]) for r in rows],index=idx)
    out={}
    for name,key,cap in VARIANTS[1:]:
        s=f[key].reindex(idx).fillna(False).astype(bool); starts=s & ~s.shift(1,fill_value=False)
        leads=[]; starts_above=0
        for dt in starts[starts].index:
            if float(lev.loc[dt])<=cap: continue
            starts_above+=1; future=lev.loc[dt:]; hit=future[future<=cap]
            if len(hit): leads.append(int(future.index.get_loc(hit.index[0])))
        out[name]={"starts_while_frozen_above_cap":starts_above,"natural_derisk_observed":len(leads),
                   "median_lead_sessions":float(pd.Series(leads).median()) if leads else None,
                   "max_lead_sessions":max(leads) if leads else None}
    return out

def _consistency(robustness):
    out={}
    names=sorted(set(x["name"] for x in robustness))
    for n in names:
        xs=[x for x in robustness if x["name"]==n]
        out[n]={"scenarios":len(xs),"drawdown_improved_fraction":sum(x["maxdd_improvement"]>0 for x in xs)/len(xs),
                "cagr_preserved_fraction":sum(x["cagr_delta"]>=0 for x in xs)/len(xs),
                "pareto_fraction":sum(x["pareto_improves_both"] for x in xs)/len(xs),
                "worst_cagr_delta":min(x["cagr_delta"] for x in xs),"worst_maxdd_improvement":min(x["maxdd_improvement"] for x in xs)}
    return out

def build(out=OUT):
    rows,tq,_,_=_aligned(); start=rows[0]["date"]; end=(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()
    close=_download(start,end); f=_augment(close)
    base=_run(rows,tq,f,None,3.0,5)
    variants=[]
    for name,key,cap in VARIANTS:
        r=_run(rows,tq,f,key,cap,5); r.update({"name":name,"signal":key,"cap":cap,"vs_baseline":_score(r,base)});variants.append(r)
    robustness=[]
    for lag in LAGS:
        lf=_lag_features(f,lag)
        for cost in COSTS:
            b=_run(rows,tq,lf,None,3.0,cost)
            for name,key,cap in VARIANTS[1:]:
                r=_run(rows,tq,lf,key,cap,cost)
                robustness.append({"lag_sessions":lag,"cost_bps":cost,"name":name,"cagr":r["cagr"],"max_drawdown":r["max_drawdown"],
                                   "cagr_delta":r["cagr"]-b["cagr"],"maxdd_improvement":r["max_drawdown"]-b["max_drawdown"],
                                   "pareto_improves_both":r["cagr"]>=b["cagr"] and r["max_drawdown"]>=b["max_drawdown"]})
    dynamic_results=[]
    for mode in DYNAMIC_MODES:
        r=_dynamic_cap_run(rows,tq,f,mode,5); r.update({"name":mode,"vs_baseline":_score(r,base)}); dynamic_results.append(r)
    dynamic_robustness=[]
    for lag in LAGS:
        lf=_lag_features(f,lag)
        # numeric state variables must also respect execution delay.
        if lag>0:
            for col in ("rv20","qdd252"):
                lf[col]=lf[col].shift(lag)
        for cost in COSTS:
            b=_run(rows,tq,lf,None,3.0,cost)
            for mode in DYNAMIC_MODES:
                r=_dynamic_cap_run(rows,tq,lf,mode,cost); dynamic_robustness.append({"lag_sessions":lag,"cost_bps":cost,"name":mode,"cagr_delta":r["cagr"]-b["cagr"],"maxdd_improvement":r["max_drawdown"]-b["max_drawdown"],"pareto_improves_both":r["cagr"]>=b["cagr"] and r["max_drawdown"]>=b["max_drawdown"]})
    result={"schema_version":1,"status":"PASS","kind":"RISK_OVERLAY_DEEP_DIVE_RESEARCH_ONLY",
      "frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,
      "hypothesis":"A short acute-volatility pulse plus an orthogonal slow-burn market-damage trigger may cover drawdowns that volatility-curve stress alone misses, without extending the acute pulse itself.",
      "variants":[{"name":n,"signal":k,"cap":c} for n,k,c in VARIANTS],
      "variant_results":variants,"dynamic_leverage_results":dynamic_results,"dynamic_leverage_robustness":{"results":dynamic_robustness,"consistency":_consistency(dynamic_robustness)},"robustness_grid":{"cost_bps":COSTS,"execution_lag_sessions":LAGS,"results":robustness},
      "episode_diagnostics":_episode_diagnostics(rows,f),
      "robustness_consistency":_consistency(robustness),
      "signal_diagnostics":_signal_diagnostics(f),
      "rolling_window_robustness":_rolling_proxy(rows,tq,f),
      "lead_time_vs_frozen":_lead_time_diagnostics(rows,f),
      "rolling_cadence":{"start_spacing_sessions":63,"windows_years":[1,3,5],"selection":"predeclared_quarterly_starts"},
      "false_alarm_cost":_false_alarm_cost(rows,tq,f),
      "pulse_contract":{"durations_sessions":[3,5,10],"caps":[2.0,1.25],"selection":"predeclared_small_mechanism_grid_not_optimizer"},
      "complement_contract":{"base":"term_severe_pulse5_cap2","fixed_additions":["momentum_break: 63-session QQQ<=-10% AND <=95% SMA200","trend_break: QQQ<=90% SMA200","credit_momentum: credit stress AND 63-session QQQ<=-8%"],"selection":"orthogonal mechanism tests; no automatic threshold search"},
      "multi_direction_contract":{"families":["realized volatility: 20d annualized >=30%","portfolio-state proxy: QQQ drawdown from 252d high <=10% or <=15%","fast shock: QQQ 5d <=-7% with fixed 5-session pulse","trend regime: below SMA200 with negative 20d return","market+credit: SPY 20d<=-5% AND HYG/LQD 20d<=-2%","hybrid: acute term pulse OR QQQ drawdown<=-10%"],"threshold_policy":"single round predeclared threshold per mechanism; no search, no winner promotion"},
      "dynamic_leverage_contract":{"modes":["continuous vol target: cap=60%/20d realized vol, bounded 1x..3x","vol tiers: 3/2.5/2/1.5x at <22/22/30/40% realized vol","drawdown budget: 3/2.5/2/1.25x at 0/-5/-10/-15% QQQ drawdown","trend+vol: minimum of trend cap2 and vol tiers","pulse+vol: minimum of pulse5 cap2 and continuous vol target","pulse+drawdown: minimum of pulse5 cap2 and drawdown budget","high-vol-only: target 75%/vol only when rv20>=25%, floor1.25","light vol tiers: 3/2.75/2.25/1.75x at <25/25/30/40% rv20","pulse+high-vol-only: minimum of pulse5 cap2 and high-vol-only","pulse+light-tiers: minimum of pulse5 cap2 and light vol tiers"],"threshold_policy":"one fixed round schedule per mechanism; no parameter sweep or winner retuning"},"anti_overfit_contract":["No automatic threshold search","No winner promotion","Frozen 8.0 unchanged","All signals use prior completed-session observations","Costs and execution lags tested as a grid"],
      "claim_boundary":"Mechanism and robustness research only. Historical success cannot establish future protection or investability."}
    Path(out).write_text(json.dumps(result,indent=2)+chr(10));return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
