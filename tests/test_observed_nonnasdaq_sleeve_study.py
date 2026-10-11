"""Toy observed bars test ledger semantics; no toy outputs reported as alpha."""
import copy
import hashlib
import pytest

from observed_nonnasdaq_sleeve_study import simulate, validate_inputs, _execute4
from observed_etf_four_challengers_batch import simulate as frozen_reference


def fixture():
    dates=["2024-03-18","2024-03-19","2024-03-20","2024-03-21","2024-03-22","2024-03-25"]
    rows=[{"date":d,"signal":"2024-03-15" if i==0 else dates[i-1],
           "l":3. if i<3 else 1.25,
           "qo":100.+i,"qc":100.5+i,
           "to":20.+i*.1,"tc":20.2+i*.1} for i,d in enumerate(dates)]
    bars={"GLD":[{"date":d,"open":200.+i,"close":200.5+i} for i,d in enumerate(dates)],
          "TLT":[{"date":d,"open":95.-.1*i,"close":95.5-.1*i} for i,d in enumerate(dates)]}
    source={"schema_version":1,"price_basis":"OBSERVED_ADJUSTED_DAILY_OPEN_CLOSE",
      "source_urls":{"GLD":"https://example.invalid/gld",
                     "TLT":"https://example.invalid/tlt"},"bars":bars}
    return rows,source


def test_frozen_whole_share_nav_parity_on_toy_observed_inputs():
    rows,source=fixture()
    for lag in (0,1):
        for slip in (10.,20.):
            x=simulate(rows,source,mode="frozen",lag=lag,
                       slip_bps=slip,attest_source=False)["navs"]
            y=frozen_reference(rows,mode="frozen",lag=lag,
                               slippage_bps=slip)["navs"]
            assert x==pytest.approx(y,abs=1e-7)


def test_portfolio_split_is_really_shares_not_synthetic_returns():
    rows,source=fixture()
    base=simulate(rows,source,mode="frozen",attest_source=False)
    for name in ("frozen85_gld075_tlt075","frozen70_gld15_tlt15"):
        a=simulate(rows,source,mode=name,attest_source=False)
        assert len(a["navs"])==len(rows)
        assert a["no_synthetic_etfs"]
        assert not a["broker_fills_verified"]
        assert a["navs"] != base["navs"]


def test_future_price_changes_cannot_modify_earlier_nav():
    rows,source=fixture()
    first=simulate(rows,source,mode="frozen85_gld075_tlt075",attest_source=False)
    newer=copy.deepcopy(source)
    newer["bars"]["GLD"][-1]["close"] *= 1.7
    second=simulate(rows,newer,mode="frozen85_gld075_tlt075",attest_source=False)
    assert first["navs"][:-1]==second["navs"][:-1]


def test_missing_or_bad_sleeve_prices_fail_closed():
    rows,source=fixture()
    source["bars"]["TLT"].pop()
    with pytest.raises(ValueError,match="SLEEVE_MISSING_FULL_REAL_ETF_COVERAGE"):
        simulate(rows,source,mode="frozen85_gld075_tlt075",attest_source=False)


def test_missing_snapshot_provenance_fails_before_research():
    rows,source=fixture()
    with pytest.raises(ValueError,match="SLEEVE_ORIGINAL_ETF_SNAPSHOT_CHANGED"):
        validate_inputs(rows,source)


def test_negative_weights_or_overspend_disallowed():
    p={"cash":100000.,"shares":{s:0 for s in ("QQQ","TQQQ","GLD","TLT")},"trades":0}
    prices={s:{"open":100.,"close":101.} for s in p["shares"]}
    with pytest.raises(ValueError,match="SLEEVE_INVALID_WEIGHTS"):
        _execute4(p,prices,{"QQQ":1.1,"TQQQ":0,"GLD":0,"TLT":0},2,10)


def test_invalid_hypothesis_or_lag_fails_closed():
    rows,source=fixture()
    with pytest.raises(ValueError,match="SLEEVE_UNREGISTERED_HYPOTHESIS"):
        simulate(rows,source,mode="optimizer_best_after_results",attest_source=False)
