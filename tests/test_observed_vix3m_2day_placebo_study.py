import pytest

from observed_vix3m_2day_placebo_study import gate_leverage, simulate, validate, MODES, THREE_MONTH_URL, BASE_SHA
from observed_etf_four_challengers_batch import simulate as older


def fixture():
    dates=["2024-03-18","2024-03-19","2024-03-20","2024-03-21"]
    market=[{"date":d,"signal":"2024-03-15" if i==0 else dates[i-1],
      "l":3.,"qo":100.+i,"qc":100.5+i,"to":20.+i/10.,"tc":20.2+i/10.}
      for i,d in enumerate(dates)]
    ix=[{"date":d,"vix_close":v} for d,v in zip(dates,[26.,30.,15.,12.])]
    longer=[{"date":d,"vix3m_close":v} for d,v in zip(dates,[23.,24.,20.,17.])]
    src={"schema_version":1,"baseline_sha256":BASE_SHA,
       "provider_first_seen_proven":False,"futures_curve_observed":False,
       "broker_fills_observed":False,
       "vix":{"series":"CBOE_VIX_INDEX_DAILY_CLOSE",
              "source_url":"https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
              "provider_publication_time_independently_verified":False,"bars":ix},
       "vix3m":{"series":"CBOE_VIX3M_93_DAY_OPTION_IMPLIED_INDEX",
              "source_url":THREE_MONTH_URL,
              "provider_historical_first_seen_verified":False,"bars":longer}}
    return market,src


def test_requires_two_prior_completed_unequal_inversions():
    mode="two_consecutive_days_cap2"
    assert gate_leverage(3.,26.,23.,30.,24.,mode)==2.
    assert gate_leverage(3.,26.,23.,20.,24.,mode)==3.
    assert gate_leverage(3.,23.,23.,30.,24.,mode)==3.
    assert gate_leverage(1.25,26.,23.,30.,24.,mode)==1.25
    assert gate_leverage(0,26.,23.,30.,24.,mode)==0.


def test_frozen_exact_previous_ledger_parity_all_four_cost_lags():
    rows,src=fixture()
    for lag in (0,1):
        for slip in (10.,20.):
            a=simulate(rows,src,mode="frozen",lag=lag,slip_bps=slip)["navs"]
            b=older(rows,mode="frozen",lag=lag,slippage_bps=slip)["navs"]
            assert a==pytest.approx(b,abs=1e-7)


def test_h2_acts_only_after_second_observed_index_close():
    rows,src=fixture()
    frozen=simulate(rows,src,mode="frozen")["navs"]
    candidate=simulate(rows,src,mode="two_consecutive_days_cap2")
    assert candidate["intervention_days"]>=1
    assert candidate["navs"]!=frozen
    assert candidate["navs"][:2]==pytest.approx(frozen[:2],abs=1e-7)


def test_mutating_future_index_does_not_modify_current():
    rows,src=fixture()
    before=simulate(rows,src,mode="two_consecutive_days_cap2")["navs"]
    src["vix"]["bars"][-1]["vix_close"]=130.
    after=simulate(rows,src,mode="two_consecutive_days_cap2")["navs"]
    assert before==after


def test_missing_index_session_blocked_no_backfill():
    rows,src=fixture()
    src["vix3m"]["bars"].pop(1)
    with pytest.raises(ValueError,match="TERM_MISSING_REAL_PREVIOUS_SESSION_INDEX"):
        validate(src,[r["date"] for r in rows])


def test_duty_matched_placebo_is_explicit_not_certified_broker_fills():
    rows,src=fixture()
    a=simulate(rows,src,mode="two_consecutive_days_cap2",slip_bps=0.,fee_bps=0.,
               placebo_indices={2})
    assert a["intervention_days"]==1
    assert a["trades"]>0
    with pytest.raises(ValueError,match="TERM_UNREGISTERED_TEST"):
        simulate(rows,src,mode="curve_fitted_after_outcome")
