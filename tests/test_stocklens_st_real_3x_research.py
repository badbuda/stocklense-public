"""Toy data verifies execution semantics, never used as research alpha."""
from datetime import date, timedelta
import copy
import pytest
from stocklens_st_real_3x_research import ETFS, weights, validate, replay, MODES

def sample(n=3100):
    start = date(2010, 3, 15)
    days=[]
    while len(days)<n:
        if start.weekday()<5:days.append(start.isoformat())
        start+=timedelta(days=1)
    level=[3.]*100+[0.]*5+[1.25]*30+[2.]*30+[3.]*(n-165)
    base={"evidence":"REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY",
          "instruments":["QQQ","TQQQ"],"live_trading_authorized":False,
          "observed_ohlc_available":True,"updated_session":days[-1],
          "daily":[{"date":d,"signal":days[i-1] if i else "2010-03-12",
                    "l":level[i],"qo":100+i*.02,"qc":100.5+i*.02,
                    "to":10+i*.01,"tc":10.2+i*.01} for i,d in enumerate(days)]}
    ext={"schema_version":1,"vendor":"YAHOO_YFINANCE_AUTO_ADJUST",
         "captured_utc":"2026-10-28T15:00:00Z","symbols":list(ETFS),
         "synthetic_prices_used":False,
         "bars":{s:[{"date":d,"open":25+i*.01,
                     "close":25.2+i*.01} for i,d in enumerate(days)] for s in ETFS}}
    return base, ext

def test_only_level_three_is_different():
    for s in ETFS:
        for level in (0,1.25,2):
            assert weights(level,"replace3_"+s)==weights(level,"frozen")
            assert weights(level,"blend25_"+s)==weights(level,"frozen")
        assert weights(3,"replace3_"+s)[s]==pytest.approx(.985)
        assert weights(3,"replace3_"+s)["TQQQ"]==0
        assert weights(3,"blend25_"+s)[s]==pytest.approx(.985*.25)
        assert weights(3,"blend25_"+s)["TQQQ"]==pytest.approx(.985*.75)

def test_market_calendar_fail_closed():
    base,ext=sample()
    rows,bars=validate(base,ext)
    assert len(rows)==3100
    ext["bars"]["SOXL"].pop(401)
    with pytest.raises(ValueError,match="MISSING_MATCHED_REAL_3X_BAR"):
        validate(base,ext)

def test_lookahead_and_fake_prices_rejected():
    b,e=sample()
    b["daily"][90]["signal"]=b["daily"][90]["date"]
    with pytest.raises(ValueError,match="FUTURE_OR_UNKNOWN"):
        validate(b,e)
    b,e=sample()
    e["synthetic_prices_used"]=True
    with pytest.raises(ValueError,match="INVALID_3X_VENDOR_SOURCE"):
        validate(b,e)

def test_unregistered_experiments_rejected():
    with pytest.raises(ValueError,match="UNREGISTERED_3X_CHALLENGER"):
        weights(3,"winner_after_search")
    assert len(MODES)==9

def test_future_bar_cannot_rewrite_past_nav():
    b,e=sample(); rows,marks=validate(b,e)
    before,_=replay(rows,marks,"blend25_SOXL",1,10.)
    changed=copy.deepcopy(e)
    changed["bars"]["SOXL"][-1]["close"]*=2.
    _,marks2=validate(b,changed)
    after,_=replay(rows,marks2,"blend25_SOXL",1,10.)
    assert before[:-1]==after[:-1] and before[-1]!=after[-1]
