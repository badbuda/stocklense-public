from paper_portfolio_integrity import evaluate
DAY="2026-10-08";SIGNAL="2026-10-07"
SNAP={SIGNAL:{"generated_at_utc":"2026-10-07T23:20:00+00:00",
              "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
              "latest":{"asof_date":SIGNAL,"qqq_weight":0.0,"tqqq_weight":.985,"target_leverage":3.}}}
def sample():
    ref=100.;fill=100.1;qty=985;gross=qty*fill;fee=gross*.0002;slip=qty*abs(ref-fill)
    cash=100000-gross-fee;equity=cash+qty*100
    row={"session_date":DAY,"signal_date":SIGNAL,"execution_source":"YFINANCE_1M_RAW",
         "target_qqq_weight":"0","target_tqqq_weight":".985","target_leverage":"3",
         "qqq_shares":"0","tqqq_shares":str(qty),"cash":str(cash),
         "qqq_close":"700","tqqq_close":"100","equity":str(equity),
         "cumulative_return":str(equity/100000-1),"fee_bps":"2","slippage_bps":"10",
         "trade_count_session":"1","turnover_notional":str(gross),
         "cumulative_fees":str(fee),"cumulative_slippage_cost":str(slip),"dividends_credited_session":"0"}
    tr={"execution_session":DAY,"signal_date":SIGNAL,"symbol":"TQQQ","side":"BUY","qty":str(qty),
        "time_et":"09:32","reference_price":str(ref),"modeled_fill_price":str(fill),
        "gross_notional":str(gross),"fee":str(fee),"modeled_slippage_cost":str(slip)}
    return row,tr
def test_empty_never_claims_trades():
    x=evaluate([],[],{})
    assert x["status"]=="WAITING_FOR_PROSPECTIVE_PAPER" and x["verified_paper_sessions"]==0
def test_good_model_is_not_broker_fill():
    a,b=sample();x=evaluate([a],[b],SNAP)
    assert x["status"]=="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS",x
    assert x["broker_fills_observed"] is False and x["live_trading_authorized"] is False
def test_synthetic_source_fails():
    a,b=sample();a["execution_source"]="QQQ_MULTIPLIED_BY_3"
    assert "SYNTHETIC_OR_UNKNOWN_SOURCE:"+DAY in evaluate([a],[b],SNAP)["errors"]
def test_lookahead_fails():
    a,b=sample();s={SIGNAL:{**SNAP[SIGNAL],"generated_at_utc":"2026-10-08T14:00:00+00:00"}}
    assert "SIGNAL_LOOKAHEAD:"+DAY in evaluate([a],[b],s)["errors"]
def test_bad_fees_fail():
    a,b=sample();a["cumulative_fees"]="0"
    assert "CUMULATIVE_FEES_INVALID:"+DAY in evaluate([a],[b],SNAP)["errors"]
def test_wrong_frozen_weight_fails():
    a,b=sample();a["target_tqqq_weight"]=".95"
    assert "TARGET_MISMATCH:"+DAY+":tqqq_weight" in evaluate([a],[b],SNAP)["errors"]
def test_wrong_fill_formula_fails():
    a,b=sample();b["modeled_fill_price"]="200"
    assert "INVALID_MODELLED_FILL:"+DAY in evaluate([a],[b],SNAP)["errors"]
def test_orphan_and_duplicate_fail():
    a,b=sample();b["execution_session"]="2026-10-09"
    issues=evaluate([a,a],[b],SNAP)["errors"]
    assert "DUPLICATE_OR_UNORDERED_SESSION" in issues and "ORPHAN_TRADE:2026-10-09" in issues
def test_second_session_cash_conservation():
    a,b=sample()
    s={"generated_at_utc":"2026-10-09T00:00:00+00:00",
       "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
       "latest":{"asof_date":"2026-10-08","qqq_weight":0.,"tqqq_weight":.985,"target_leverage":3.}}
    nxt={**a,"session_date":"2026-10-09","signal_date":"2026-10-08",
         "trade_count_session":"0","turnover_notional":"0"}
    assert evaluate([a,nxt],[b],{**SNAP,"2026-10-08":s})["status"]=="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"
    nxt["cash"]=str(float(nxt["cash"])+50)
    assert "CASH_CONSERVATION_INVALID:2026-10-09" in evaluate([a,nxt],[b],{**SNAP,"2026-10-08":s})["errors"]
