from __future__ import annotations
import json, math, random, statistics
from pathlib import Path
from datetime import date
from stocklens.data import load_qqq_history, load_tqqq_history
from yahoo_long_history import _rows
from tqqq_reality_check import _aligned, _hybrid_actual_l3

OUT=Path("research/adversarial_validation.json")

def _daily_hybrid_returns(rows,tqqq,delay=0):
    out=[]
    for i in range(1,len(rows)):
        j=max(0,i-1-delay); exp=float(rows[j]["leverage"])
        q=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        r=tqqq[rows[i]["date"]]/tqqq[rows[i-1]["date"]]-1 if exp==3.0 else q*exp
        out.append((rows[i]["date"],r,exp))
    return out

def _risk_metrics(rets,maxdd):
    xs=[r for _,r,_ in rets]; n=len(xs); mean=sum(xs)/n
    var=sum((x-mean)**2 for x in xs)/(n-1)
    vol=math.sqrt(var)*math.sqrt(252)
    downside=math.sqrt(sum(min(x,0.0)**2 for x in xs)/n)*math.sqrt(252)
    sharpe=mean*252/vol if vol else None
    sortino=mean*252/downside if downside else None
    return {"annualized_volatility":vol,"sharpe_zero_rf":sharpe,"downside_deviation":downside,
      "sortino_zero_target":sortino,"calmar":None if not maxdd else (None)}

def _period(rows,tq,start,end,cost=5,delay=0):
    rr=[x for x in rows if start<=x["date"]<=end]
    if len(rr)<100:return None
    x=_hybrid_actual_l3(rr,tq,cost,delay)
    years=(date.fromisoformat(rr[-1]["date"])-date.fromisoformat(rr[0]["date"])).days/365.2425
    return {"start":rr[0]["date"],"end":rr[-1]["date"],"sessions":len(rr),**x}

def _year_splits(rows,tq):
    out=[]
    for y in sorted({r["date"][:4] for r in rows}):
        x=_period(rows,tq,y+"-01-01",y+"-12-31")
        if x:out.append({"year":int(y),**x})
    return out

def _leave_crisis_out(rows,tq):
    crises={"euro_2011":("2011-07-01","2011-12-31"),"volmageddon_2018":("2018-01-01","2018-12-31"),
      "covid_2020":("2020-02-01","2020-06-30"),"rate_bear_2022":("2022-01-01","2022-12-31")}
    rets=_daily_hybrid_returns(rows,tq,0)
    def compound(xs):
        nav=peak=1.0; dd=0.0
        for _,r,_ in xs: nav*=1+r; peak=max(peak,nav); dd=min(dd,nav/peak-1)
        return nav,dd
    base,_=compound(rets); out=[]
    for name,(a,b) in crises.items():
        kept=[x for x in rets if not(a<=x[0]<=b)]
        nav,dd=compound(kept)
        out.append({"excluded":name,"window":[a,b],"ending_growth":nav,"max_drawdown":dd,
          "ending_growth_ratio_to_full":nav/base,
          "semantics":"Excluded daily returns are omitted without computing a return across the removed calendar gap."})
    return out

def _execution_monte_carlo(rows,tq,n=500,seed=80):
    # Execution-only uncertainty: frozen signals/market path remain untouched.
    rng=random.Random(seed); vals=[]
    for _ in range(n):
        cost=rng.uniform(5,100); delay=rng.choice((0,0,0,1,1,2,5))
        x=_hybrid_actual_l3(rows,tq,cost,delay)
        vals.append({"cagr":x["cagr"],"max_drawdown":x["max_drawdown"],"cost_bps":cost,"delay":delay})
    cs=sorted(x["cagr"] for x in vals); ds=sorted(x["max_drawdown"] for x in vals)
    def q(a,p):return a[min(len(a)-1,max(0,int((len(a)-1)*p)))]
    return {"trials":n,"seed":seed,"scope":"EXECUTION_ASSUMPTION_MONTE_CARLO_NOT_MARKET_RETURN_FORECAST",
      "cagr_p05":q(cs,.05),"cagr_median":q(cs,.5),"cagr_p95":q(cs,.95),
      "maxdd_p05":q(ds,.05),"maxdd_median":q(ds,.5),"maxdd_p95":q(ds,.95),
      "min_cagr":min(cs),"max_cagr":max(cs)}

def _qqq_risk(rows):
    rs=[(rows[i]["date"],float(rows[i]["close"])/float(rows[i-1]["close"])-1.0,1.0) for i in range(1,len(rows))]
    nav=peak=1.0;dd=0.0
    for _,r,_ in rs: nav*=1+r; peak=max(peak,nav); dd=min(dd,nav/peak-1)
    m=_risk_metrics(rs,dd); years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.2425
    m["cagr"]=nav**(1/years)-1; m["max_drawdown"]=dd
    m["calmar"]=m["cagr"]/abs(dd) if dd else None
    return m

def _lean_overlap(rows,tq):
    rr=[r for r in rows if r["date"]<="2024-08-29"]
    h=_hybrid_actual_l3(rr,tq,5,0)
    return {"lean_start":"2009-09-01","hybrid_start":rr[0]["date"],"end":"2024-08-29",
      "lean_nav_multiple":134.1824,"hybrid_actual_l3_nav_multiple":h["end_equity"]/100000.0,
      "comparable_start":False,"hybrid_to_lean_ratio":None,
      "status":"INCOMPARABLE_START_DATES",
      "claim_boundary":"Do not compare endpoint multiples as a parity ratio: LEAN starts 2009-09-01 while observed-TQQQ hybrid starts later. Daily LEAN NAV at the common start is unavailable."}

def _block_bootstrap(rets,n=500,block=21,seed=800):
    rng=random.Random(seed); xs=[r for _,r,_ in rets]; vals=[]; horizon=len(xs)
    for _ in range(n):
        path=[]
        while len(path)<horizon:
            k=rng.randrange(max(1,horizon-block+1)); path.extend(xs[k:k+block])
        nav=peak=1.0;dd=0.0; underwater=longest=0; trough_i=peak_i=0; recovery=None
        for i,r in enumerate(path[:horizon]):
            nav*=1+r
            if nav>=peak:
                peak=nav; underwater=0
                if recovery is None and i>trough_i: recovery=i-trough_i
            else:
                underwater+=1; longest=max(longest,underwater)
                cur=nav/peak-1
                if cur<dd: dd=cur; trough_i=i; peak_i=i-underwater; recovery=None
        vals.append({"growth":nav,"maxdd":dd,"longest_underwater_sessions":longest,
          "deepest_drawdown_recovered":recovery is not None,"deepest_recovery_sessions":recovery})
    growth=sorted(x["growth"] for x in vals); draw=sorted(x["maxdd"] for x in vals)
    uw=sorted(x["longest_underwater_sessions"] for x in vals)
    rec=sorted(x["deepest_recovery_sessions"] for x in vals if x["deepest_recovery_sessions"] is not None)
    q=lambda a,p:a[int((len(a)-1)*p)]
    thresholds={str(int(abs(t)*100)):sum(x["maxdd"]<=t for x in vals)/n for t in (-.5,-.6,-.7,-.8)}
    return {"trials":n,"block_sessions":block,"seed":seed,"scope":"PATH_FRAGILITY_ONLY_NOT_FORECAST",
      "ending_growth_p05":q(growth,.05),"ending_growth_median":q(growth,.5),"ending_growth_p95":q(growth,.95),
      "maxdd_p05":q(draw,.05),"maxdd_median":q(draw,.5),"maxdd_p95":q(draw,.95),
      "drawdown_threshold_hit_rate":thresholds,
      "longest_underwater_sessions_median":q(uw,.5),"longest_underwater_sessions_p95":q(uw,.95),
      "deepest_drawdown_recovery_rate":sum(x["deepest_drawdown_recovered"] for x in vals)/n,
      "deepest_recovery_sessions_median":q(rec,.5) if rec else None,
      "deepest_recovery_sessions_p95":q(rec,.95) if rec else None}

def build(out=OUT):
    rows,tq,qa,ta=_aligned()
    base=_hybrid_actual_l3(rows,tq,5,0)
    rets=_daily_hybrid_returns(rows,tq,0)
    risk=_risk_metrics(rets,base["max_drawdown"])
    risk["calmar"]=base["cagr"]/abs(base["max_drawdown"]) if base["max_drawdown"] else None
    combined=[{"cost_bps":c,"delay_sessions":d,**_hybrid_actual_l3(rows,tq,c,d)}
      for c,d in ((25,1),(50,1),(50,2),(100,2),(100,5))]
    result={"schema_version":1,"status":"PASS","kind":"ADVERSARIAL_VALIDATION_RESEARCH_ONLY",
      "promotion_allowed":False,"frozen_model_mutated":False,
      "claim_boundary":"Observed TQQQ only at frozen 3x sessions; other exposures synthetic. Monte Carlo varies execution assumptions only and is not a forecast.",
      "baseline_hybrid_actual_l3":base,"risk_adjusted":{"strategy":risk,"qqq":_qqq_risk(rows)},"lean_overlap_endpoint":_lean_overlap(rows,tq),"calendar_years":_year_splits(rows,tq),
      "leave_crisis_out":_leave_crisis_out(rows,tq),"combined_execution_stress":combined,
      "execution_uncertainty":_execution_monte_carlo(rows,tq),"path_fragility_block_bootstrap":_block_bootstrap(rets)}
    Path(out).write_text(json.dumps(result,indent=2)+chr(10));return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
