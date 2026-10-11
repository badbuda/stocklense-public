"""Test only fabricated index rates and ETF prices. No toy market performance claims."""
import pytest
from observed_vix3m_term_structure_study import (
    capped_leverage,validate,simulate,MODES,THREE_MONTH_URL,BASE_SHA)
from observed_etf_four_challengers_batch import simulate as frozen_sim


def sample():
    dates=["2024-03-18","2024-03-19","2024-03-20","2024-03-21"]
    market=[{"date":d,"signal":"2024-03-15" if i==0 else dates[i-1],
        "l":3.,"qo":100+i,"qc":100.5+i,
        "to":20+i*.1,"tc":20.2+i*.1} for i,d in enumerate(dates)]
    vix=[{"date":d,"vix_close":v} for d,v in zip(dates,[20.,30.,15.,12.])]
    term=[{"date":d,"vix3m_close":v} for d,v in zip(dates,[23.,24.,20.,17.])]
    src={"schema_version":1,"baseline_sha256":BASE_SHA,"provider_first_seen_proven":False,
       "futures_curve_observed":False,"broker_fills_observed":False,
       "vix":{"series":"CBOE_VIX_INDEX_DAILY_CLOSE",
              "source_url":"https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
              "provider_publication_time_independently_verified":False,"bars":vix},
       "vix3m":{"series":"CBOE_VIX3M_93_DAY_OPTION_IMPLIED_INDEX",
             "source_url":THREE_MONTH_URL,
             "provider_historical_first_seen_verified":False,"bars":term}}
    return market,src


def test_ratio_only_prior_complete_close_and_defense_respected():
    assert capped_leverage(3,25.,24.,"term_inversion_cap2")==2.
    assert capped_leverage(3,20.,24.,"term_inversion_cap2")==3.
    assert capped_leverage(0,100.,10.,"term_inversion_cap2")==0.
    assert capped_leverage(1.25,100.,10.,"term_inversion_cap2")==1.25


def test_frozen_bitwise_nav_parity_for_both_extra_lags():
    market,src=sample()
    for lag in (0,1):
        for slip in (10.,20.):
            a=simulate(market,src,mode="frozen",lag=lag,slip_bps=slip)["navs"]
            b=frozen_sim(market,mode="frozen",lag=lag,slippage_bps=slip)["navs"]
            assert a==pytest.approx(b,abs=1e-7)


def test_today_index_change_never_changes_today_position():
    market,src=sample()
    x=simulate(market,src,mode="term_inversion_cap2")["navs"]
    src["vix"]["bars"][-1]["vix_close"]=155.
    src["vix3m"]["bars"][-1]["vix3m_close"]=5.
    assert simulate(market,src,mode="term_inversion_cap2")["navs"]==x


def test_inverted_term_structure_changes_physical_equity_path():
    market,src=sample()
    frozen=simulate(market,src,mode="frozen")["navs"]
    candidate=simulate(market,src,mode="term_inversion_cap2")
    assert candidate["navs"]!=frozen
    assert candidate["intervention_days"]>=1


def test_missing_real_cboe_session_refuses_to_fill():
    market,src=sample()
    src["vix3m"]["bars"].pop(1)
    with pytest.raises(ValueError,match="TERM_MISSING_REAL_PREVIOUS_SESSION_INDEX"):
        simulate(market,src,mode="term_inversion_cap2")


def test_invalid_index_and_self_attestation_fail_closed():
    market,src=sample()
    src["provider_first_seen_proven"]=True
    with pytest.raises(ValueError,match="TERM_UNTRUSTED_PROVENANCE"):
        validate(src,[r["date"] for r in market])
    market,src=sample()
    src["vix3m"]["bars"][1]["vix3m_close"]=-1
    with pytest.raises(ValueError,match="TERM_INVALID_ORDER_OR_PRICE"):
        validate(src,[r["date"] for r in market])


def test_unregistered_rules_and_invalid_values_rejected():
    with pytest.raises(ValueError,match="TERM_UNREGISTERED_EXPOSURE"):
        capped_leverage(3,20.,19.,"optimized_after_hindsight")
    with pytest.raises(ValueError,match="TERM_PRIOR_INDEX_INVALID"):
        capped_leverage(3,20.,0.,"term_inversion_cap2")
