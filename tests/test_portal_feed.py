"""Fail-closed UI feed projections; tests use no Yahoo/network/AWS."""
from copy import deepcopy
import pytest
from portal_feed import build

def fixture():
    dates=[f"2026-09-{i:02d}" for i in range(1,22)]
    rows=[{"date":date,"stocklens_nav":100000+i*100.0,
           "qqq_nav":100000+i*70.0,"leverage":3.0,
           "effective_prior_signal_date":dates[max(0,i-1)],
           "rebalance":i==0,"contribution":0}
          for i,date in enumerate(dates)]
    return {
        "status":"PASS",
        "kind":"OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY",
        "observed_instruments":["QQQ","TQQQ"],
        "broker_fills_observed":False,
        "price_source":"YFINANCE_AUTO_ADJUSTED_DAILY_OPEN_AND_CLOSE",
        "price_fingerprint_sha256":"f"*64,
        "observed_price_snapshot":{"sha256":"0"*64},
        "period":{"start":dates[0],"end":dates[-1],"sessions":len(rows)},
        "limitations":["Not broker fills"],
        "no_contributions":{
            "start":dates[0],"end":dates[-1],"sessions":len(rows),
            "daily_nav_rows":rows,
            "stocklens":{"ending_equity":rows[-1]["stocklens_nav"]},
            "qqq_buy_hold":{"ending_equity":rows[-1]["qqq_nav"]}},
        "initial_100k_monthly_3500":{
            "monthly_contribution":3500,
            "stocklens":{"ending_equity":105000},
            "qqq_buy_hold":{"ending_equity":104000}},
        "slippage_stress_no_contributions":[],
        "signal_lag_stress_no_contributions":[]
    }


def test_verified_observed_etf_feed_has_no_invented_prices(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    data=build(fixture())
    assert len(data["daily"])==21
    assert data["daily"][0]["s"]==100000
    assert data["daily"][0]["q"]==100000
    assert not data["observed_ohlc_available"]
    assert "to" not in data["daily"][0]  # never invent missing TQQQ
    assert not data["live_trading_authorized"]


def test_rejects_fake_broker_evidence(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    data=fixture();data["broker_fills_observed"]=True
    with pytest.raises(ValueError,match="REAL_ETF_OR_BROKER"):
        build(data)


def test_rejects_gaps_and_inconsistent_nav(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    data=fixture();data["no_contributions"]["daily_nav_rows"].pop()
    with pytest.raises(ValueError,match="NO_COMPLETE"):
        build(data)
    data=fixture();data["no_contributions"]["stocklens"]["ending_equity"]=5
    with pytest.raises(ValueError,match="ENDING_EQUITY"):
        build(data)


def test_only_matching_hashed_raw_yahoo_tqqq_prices_are_consumed(tmp_path,monkeypatch):
    import hashlib
    monkeypatch.chdir(tmp_path)
    folder=tmp_path/"research"/"data"
    folder.mkdir(parents=True)
    dates=[f"2026-09-{i:02d}" for i in range(1,22)]
    raw="date,qqq_adjusted_open,qqq_adjusted_close,tqqq_adjusted_open,tqqq_adjusted_close\n"+"".join(f"{d},100,101,50,51\n" for d in dates)
    (folder/"observed_etf_qqq_tqqq_adjusted.csv").write_text(raw)
    data=fixture()
    data["observed_price_snapshot"]["sha256"]=hashlib.sha256(raw.encode()).hexdigest()
    p=build(data)
    assert p["observed_ohlc_available"] is True
    assert p["daily"][0]["to"]==50 and p["daily"][0]["tc"]==51
    data["observed_price_snapshot"]["sha256"]="0"*64
    with pytest.raises(ValueError,match="YAHOO_PRICE_SNAPSHOT_HASH_DRIFT"):
        build(data)
