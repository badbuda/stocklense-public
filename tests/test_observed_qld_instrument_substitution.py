"""Tiny fabricated test fixtures are tests only, NEVER reported as market return."""
import pandas as pd
import pytest

from observed_qld_instrument_substitution import (
    target_weights, normalize_price_frame, freeze_source,simulate,
)
from observed_etf_four_challengers_batch import simulate as ref
from stocklens.core import TARGET_INVESTED_FRACTION as F


def fake():
    dates=["2024-03-18","2024-03-19","2024-03-20","2024-03-21"]
    rows=[{"date":d,"signal":"2024-03-15" if not i else dates[i-1],
           "l":[2,2,1.25,3][i],"qo":100.+i,"qc":100.5+i,
           "to":20.+i/10.,"tc":20.2+i/10.} for i,d in enumerate(dates)]
    b=[{"date":d,"open":40.+i,"close":40.5+i} for i,d in enumerate(dates)]
    return rows,freeze_source(rows,b)


def test_qld_substitution_exact_instruments_not_synthetic_qqq_returns():
    x=target_weights(2,"qld_only_at_2x")
    assert x["QLD"]==F and x["QQQ"]==0 and x["TQQQ"]==0
    y=target_weights(1.25,"qld_at_1_25x_and_2x")
    assert y["QQQ"]==pytest.approx(F*.75)
    assert y["QLD"]==pytest.approx(F*.25)
    assert y["TQQQ"]==0
    assert target_weights(3,"qld_at_1_25x_and_2x")["TQQQ"]==F
    assert sum(target_weights(0,"qld_only_at_2x").values())==0


def test_frozen_daily_nav_parity_with_older_engine():
    rows,src=fake()
    for lag in (0,1):
        for slip in (10.,20.):
            a=simulate(rows,src,"frozen",lag,slip)["navs"]
            b=ref(rows,mode="frozen",lag=lag,slippage_bps=slip)["navs"]
            assert a==pytest.approx(b,abs=1e-7)


def test_challenger_instrument_prices_actually_change_ledger():
    rows,source=fake()
    a=simulate(rows,source,"frozen")["navs"]
    b=simulate(rows,source,"qld_only_at_2x")["navs"]
    assert a!=b


def test_price_source_calendar_gap_fails_closed():
    rows,source=fake()
    source["bars"].pop()
    with pytest.raises(ValueError,match="QLD_DATE_MISMATCH"):
        simulate(rows,source)


def test_missing_real_ohlc_not_forwardfilled():
    frame=pd.DataFrame({"Open":[20.,21.],"Close":[21.,22.]},
        index=pd.to_datetime(["2024-03-18","2024-03-20"]))
    with pytest.raises(ValueError,match="QLD_MISSING_OBSERVED_TRADING_DAYS"):
        normalize_price_frame(frame,["2024-03-18","2024-03-19","2024-03-20"])


def test_negative_or_duplicate_ohlc_rejected():
    a=pd.DataFrame({"Open":[20.,float("nan")],"Close":[21.,22.]},
        index=pd.to_datetime(["2024-03-18","2024-03-19"]))
    with pytest.raises(ValueError,match="QLD_NONFINITE_OR_ZERO"):
        normalize_price_frame(a,["2024-03-18"])
    b=pd.concat([a.iloc[:1],a.iloc[:1]])
    with pytest.raises(ValueError,match="QLD_DUPLICATE"):
        normalize_price_frame(b,["2024-03-18"])


def test_contract_rejects_fake_proof_flags_or_synthetic_returns():
    rows,source=fake()
    source["first_seen_proven"]=True
    with pytest.raises(ValueError,match="QLD_UNVERIFIED_SOURCE"):
        simulate(rows,source)


def test_cannot_invent_unregistered_hypothesis():
    rows,source=fake()
    with pytest.raises(ValueError,match="QLD_HYPOTHESIS_NOT_REGISTERED"):
        simulate(rows,source,mode="best_optimized_after_data")
