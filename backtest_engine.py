from __future__ import annotations
import hashlib, json, math
from datetime import date
from dataclasses import asdict
from typing import Mapping, Any, Sequence
from backtest_contract import BacktestRequest, StrategyAdapter

def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",",":")).encode()).hexdigest()

def run_backtest(rows: Sequence[Mapping[str, Any]], request: BacktestRequest, strategy: StrategyAdapter) -> dict:
    """Deterministic single-asset replay engine for M2.

    This is a generic research replay engine, not LEAN execution parity.
    Strategy supplies target exposure; engine owns capital, contributions,
    turnover-cost accounting, drawdown and deterministic provenance.
    """
    strategy.validate_rows(rows)
    if request.strategy_id != strategy.strategy_id:
        raise ValueError("BACKTEST_STRATEGY_ID_MISMATCH")
    request_numbers=(float(request.initial_capital),float(request.monthly_contribution),float(request.transaction_cost_bps))
    if not all(math.isfinite(x) for x in request_numbers) or request_numbers[0] <= 0 or request_numbers[1] < 0 or request_numbers[2] < 0:
        raise ValueError("BACKTEST_REQUEST_INVALID")
    selected=[dict(r) for r in rows if (request.start is None or r["date"]>=request.start) and (request.end is None or r["date"]<=request.end)]
    if len(selected)<2:
        raise ValueError("BACKTEST_WINDOW_TOO_SHORT")
    nav=paid=float(request.initial_capital)
    peak=nav
    legacy_nav_maxdd=0.0
    twr_index=twr_peak=1.0
    maxdd=0.0
    total_cost=0.0
    last_month=selected[0]["date"][:7]
    ledger=[{"date":selected[0]["date"],"contribution":float(request.initial_capital),"exposure":0.0,"gross_market_pl":0.0,"estimated_cost":0.0,"net_nav":nav,"paid_capital":paid,"drawdown":0.0,"twr_index":1.0,"twr_daily_return":0.0}]
    previous_exposure=0.0
    for i in range(1,len(selected)):
        current,previous=selected[i],selected[i-1]
        contribution=0.0
        month=current["date"][:7]
        if month!=last_month:
            contribution=float(request.monthly_contribution)
            nav+=contribution
            paid+=contribution
            last_month=month
        starting_nav_after_cashflow=nav
        exposure=float(strategy.target_exposure(previous,current))
        if not math.isfinite(exposure):
            raise ValueError("BACKTEST_EXPOSURE_NON_FINITE")
        qret=float(current["close"])/float(previous["close"])-1.0
        gross_pl=nav*qret*exposure
        nav_before_cost=nav+gross_pl
        if not math.isfinite(nav_before_cost) or nav_before_cost<=0:
            raise RuntimeError("BACKTEST_CAPITAL_DEPLETED_BEFORE_COST")
        turnover=float(strategy.transaction_turnover(previous,current,previous_exposure,exposure))
        if not math.isfinite(turnover) or turnover < 0:
            raise ValueError("BACKTEST_TURNOVER_INVALID")
        cost=nav_before_cost*turnover*float(request.transaction_cost_bps)/10000.0
        nav=nav_before_cost-cost
        total_cost+=cost
        daily_twr_return=nav/starting_nav_after_cashflow-1.0
        twr_index*=1.0+daily_twr_return
        twr_peak=max(twr_peak,twr_index)
        dd=twr_index/twr_peak-1.0
        maxdd=min(maxdd,dd)
        peak=max(peak,nav)
        legacy_nav_maxdd=min(legacy_nav_maxdd,nav/peak-1.0)
        ledger.append({"date":current["date"],"contribution":contribution,"exposure":exposure,"gross_market_pl":gross_pl,"turnover":turnover,"estimated_cost":cost,"net_nav":nav,"paid_capital":paid,"drawdown":dd,"twr_index":twr_index,"twr_daily_return":daily_twr_return})
        previous_exposure=exposure
    if not all(math.isfinite(x) for x in (nav,paid,maxdd,total_cost)) or nav<=0:
        raise RuntimeError("BACKTEST_INVALID_CAPITAL_PATH")
    request_dict=asdict(request)
    years=max((date.fromisoformat(selected[-1]["date"])-date.fromisoformat(selected[0]["date"])).days/365.2425,1/365.2425)
    cagr=(nav/float(request.initial_capital))**(1/years)-1 if request.monthly_contribution==0 else None
    # Contribution-neutral: each daily return uses starting NAV after external cashflow.
    daily_returns=[row["twr_daily_return"] for row in ledger[1:]]
    mean_ret=sum(daily_returns)/len(daily_returns) if daily_returns else 0.0
    variance=sum((x-mean_ret)**2 for x in daily_returns)/(len(daily_returns)-1) if len(daily_returns)>1 else 0.0
    annualized_volatility=math.sqrt(variance)*math.sqrt(252.0)
    sharpe_proxy=(mean_ret*252.0/annualized_volatility) if annualized_volatility>0 else None
    total_turnover=sum(float(x.get("turnover",0.0)) for x in ledger)
    analytics={
        "cagr_without_contribution_distortion":cagr,
        "time_weighted_return":twr_index-1.0,
        "time_weighted_growth_index":twr_index,
        "time_weighted_max_drawdown":maxdd,
        "legacy_cashflow_distorted_nav_drawdown":legacy_nav_maxdd,
        "annualized_volatility_proxy":annualized_volatility,
        "sharpe_proxy_zero_risk_free":sharpe_proxy,
        "total_turnover_proxy":total_turnover,
        "cost_to_paid_capital":total_cost/paid if paid else None,
        "ending_to_paid_capital_multiple":nav/paid if paid else None,
        "semantics":"Generic close-to-close replay, not broker execution. CAGR omitted with contributions; volatility, Sharpe and drawdown are contribution-neutral TWR.",
    }
    return {
        "schema_version":1,
        "kind":"GENERIC_BACKTEST_RESULT",
        "status":"PASS",
        "strategy_id":strategy.strategy_id,
        "evidence_class":strategy.evidence_class,
        "execution_parity":False,
        "request":request_dict,
        "request_sha256":_fingerprint(request_dict),
        "rows_sha256":_fingerprint(selected),
        "sessions":len(selected),
        "start":selected[0]["date"],
        "end":selected[-1]["date"],
        "end_equity":nav,
        "paid_capital":paid,
        "replay_profit_loss":nav-paid,
        "max_drawdown":maxdd,
        "total_estimated_transaction_cost":total_cost,
        "analytics":analytics,
        "ledger":ledger,
        "ledger_sha256":_fingerprint(ledger),
    }
