"""Decision register must not conflate Shadow, historical proxy, Paper, or AWS."""
from datetime import datetime
import json
from pathlib import Path
import pytest
from decision_register_publish import build, extract_shadow, KIND

def signal(day, *, action="NO_CHANGE"):
    return {
        "version": "8.0.2-shadow-completed-session-guard",
        "generated_at_utc": day + "T23:30:00+00:00",
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE",
        "latest": {"asof_date": day, "level": 3, "defense_active": False,
                   "target_leverage": 3, "qqq_weight": 0, "tqqq_weight": .985,
                   "features": {"close": 700}},
        "action": action,
        "execution_plan": {"broker_actions_enabled": False},
    }

def historical():
    dates = [f"2026-01-{i:02d}" for i in range(1,29)]
    # Source contract requires >=100 historical rows; only dates and count
    # matter to the registration function, not execution math.
    rows = [{"date":f"2025-{i//28+1:02d}-{i%28+1:02d}", "l":3, "signal":"2025-01-01",
             "rebalance":False,"qo":100,"to":50} for i in range(112)]
    return {"evidence":"REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY",
            "observed_ohlc_available":True,"live_trading_authorized":False,
            "full_lean_broker_parity":False,
            "period":{"start":rows[0]["date"],"end":rows[-1]["date"],"sessions":len(rows)},
            "updated_session":rows[-1]["date"],"daily":rows}

def paper():
    return {"broker_fills_observed":False,"session_date":"2026-10-09",
            "row":{"session_date":"2026-10-09","equity":98696.78}}

def write_sig(d, day, **kwargs):
    p = d / (day+".json")
    p.write_text(json.dumps(signal(day,**kwargs)),encoding="utf-8")
    return p

def test_real_saved_days_only_and_historical_marked(tmp_path):
    a=write_sig(tmp_path,"2026-10-09")
    b=write_sig(tmp_path,"2026-10-28")
    output=build([a,b],historical(),paper())
    assert output["kind"]==KIND
    assert output["archived_signal_count"]==2
    assert [v["session"] for v in output["archived_signals"]]==["2026-10-09","2026-10-28"]
    assert output["missing_signal_days_filled"] is False
    assert output["archive_is_contiguous"] is False
    assert output["historical_execution_proxy"]["sessions"]==112
    assert "HISTORICAL_MODELED" in output["historical_execution_proxy"]["label"]
    assert output["legacy_paper"]["last_recorded_session"]=="2026-10-09"
    assert output["aws_st"]["status"]=="REQUIRES_AUTHENTICATED_AWS_READBACK"
    assert output["automatic_trading_authorized"] is False
    assert output["broker_orders_executed_by_this_report"] is False

def test_reject_broker_enabled_shadow(tmp_path):
    p=write_sig(tmp_path,"2026-10-28")
    x=json.loads(p.read_text());x["execution_plan"]["broker_actions_enabled"]=True
    p.write_text(json.dumps(x))
    with pytest.raises(ValueError,match="INVALID_SHADOW_ARCHIVE"):extract_shadow(p)

def test_reject_misdated_shadow_file(tmp_path):
    p=tmp_path/"2026-10-27.json";p.write_text(json.dumps(signal("2026-10-28")))
    with pytest.raises(ValueError,match="INVALID_SHADOW_ARCHIVE"):extract_shadow(p)

def test_reject_broker_fill_in_paper(tmp_path):
    p=write_sig(tmp_path,"2026-10-28")
    x=paper();x["broker_fills_observed"]=True
    with pytest.raises(ValueError,match="INVALID_LEGACY_PAPER_ARCHIVE"):build([p],historical(),x)

def test_portal_source_contract():
    html=Path("docs/decisions.html").read_text(encoding="utf-8")
    assert "decision-register.json" in html
    assert "portal-history.json" in html
    assert "HISTORICAL_MODELED_DAILY_OPEN_NOT_BROKER" in html
    assert "archived_signals" in html
    assert "fetch(u,{cache:'no-store'})" in html
    assert '<script type="module">' in html
    assert "innerHTML" not in html
    assert "stocklens-archived-shadow-decisions.csv" in html
    assert "stocklens-historical-modeled-decisions.csv" in html

def test_published_current_register_matches_repository_sources():
    from decision_register_publish import SHADOW, HISTORY, PAPER
    report=build(sorted(SHADOW.glob("20??-??-??.json")),
                 json.loads(HISTORY.read_text()),json.loads(PAPER.read_text()))
    published=json.loads(Path("docs/decision-register.json").read_text(encoding="utf-8"))
    assert report == published
