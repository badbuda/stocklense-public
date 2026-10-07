from __future__ import annotations
import math, statistics

def evaluate_daily_returns(returns):
    xs=[float(x) for x in returns]
    if not xs:return {"sessions":0}
    nav=peak=1.0;maxdd=0.0;down=[]
    for r in xs:
        nav*=1+r;peak=max(peak,nav);maxdd=min(maxdd,nav/peak-1)
        if r<0:down.append(r)
    n=len(xs);years=n/252.0
    cagr=nav**(1/years)-1 if years>0 and nav>0 else None
    mean=statistics.fmean(xs);vol=statistics.pstdev(xs)*math.sqrt(252) if n>1 else 0.0
    downside=math.sqrt(statistics.fmean([min(0.0,r)**2 for r in xs]))*math.sqrt(252)
    sharpe=(mean*252/vol) if vol else None
    sortino=(mean*252/downside) if downside else None
    calmar=(cagr/abs(maxdd)) if cagr is not None and maxdd<0 else None
    return {"sessions":n,"ending_growth":nav,"cagr":cagr,"max_drawdown":maxdd,
      "annualized_volatility":vol,"sharpe_zero_rf":sharpe,"sortino_zero_target":sortino,"calmar":calmar}
