"""Forced BUY/SELL/NO_CHANGE/CASH lifecycle against REAL StockLens paper code.

All 16 exposure transitions + multi-day persisted ledger/receipts and sabotage
cases. Market bars/signals are deterministic SYNTHETIC fixtures ONLY.
No Lambda, S3, internet data, user paper book, broker or production mutations.
A green result does NOT certify any deployed private AWS Paper handler.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy

import exchange_calendars as xcals
import pytest

from stocklens.core import LEVEL_LEVERAGE, TARGET_INVESTED_FRACTION, weights_for_leverage
from stocklens.paper import (
    SessionMarket, PaperIntegrityError, new_state, rebalance_if_required,
    mark_session, _apply_corporate_actions, _trade,
)
import paper_portfolio
from paper_portfolio_integrity import evaluate as independent_accounting
from paper_transaction import commit as persist_paper, recover as recover_paper

STATES = ("CASH", "L1", "L2", "L3")
TRANSITIONS = tuple(itertools.product(STATES, repeat=2))
MODELLED_BROKER_FILLS = False


def signal(prior_day: str, target: str, *, action: str = "NO_CHANGE") -> dict:
    assert target in STATES
    level = int(target[-1]) if target != "CASH" else 1
    defended = target == "CASH"
    lev = 0.0 if defended else LEVEL_LEVERAGE[level]
    q, t = weights_for_leverage(lev)
    return {
        "action": action,
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "generated_at_utc": prior_day + "T23:00:00Z",
        "execution_plan": {"broker_actions_enabled": False},
        "latest": {
            "asof_date": prior_day, "level": level,
            "defense_active": defended, "target_leverage": lev,
            "qqq_weight": q * TARGET_INVESTED_FRACTION,
            "tqqq_weight": t * TARGET_INVESTED_FRACTION,
        },
    }


def market(day, *, q31=100., t31=50., q32=None, t32=None,
           qclose=None, tclose=None, dividend=None, split=None):
    return SessionMarket(
        day, {"QQQ":q31,"TQQQ":t31},
        {"QQQ":q31 if q32 is None else q32,
         "TQQQ":t31 if t32 is None else t32},
        {"QQQ":q31 if qclose is None else qclose,
         "TQQQ":t31 if tclose is None else tclose},
        dividend or {"QQQ":0.,"TQQQ":0.},
        split or {"QQQ":0.,"TQQQ":0.},
    )


def step(state, s, m, *, bootstrap=False):
    corporate = _apply_corporate_actions(state, m)
    trades = rebalance_if_required(state, s, m, bootstrap)
    row = mark_session(state, s, m, trades, corporate, bootstrap)
    assert row["execution_source"] == "YFINANCE_1M_RAW"  # fixture label, not real feed
    assert state["cash"] >= -1e-7
    assert all(isinstance(n,int) and n>=0 for n in state["shares"].values())
    assert row["trade_count_session"] == len(trades)
    assert row["turnover_notional"] == pytest.approx(
        sum(t["gross_notional"] for t in trades), abs=1e-7)
    assert row["cumulative_fees"] >= 0
    assert row["cumulative_slippage_cost"] >= 0
    assert row["target_tracking_gap_after"] <= .01 + 1e-9
    assert [x["side"] for x in trades] == sorted(
        [x["side"] for x in trades], key=lambda side: 0 if side=="SELL" else 1)
    for tr in trades:
        assert tr["symbol"] in ("QQQ","TQQQ")
        assert tr["side"] in ("SELL","BUY")
        assert tr["time_et"] == ("09:31" if tr["side"]=="SELL" else "09:32")
        assert tr["signal_date"] == s["latest"]["asof_date"]
        assert tr["qty"] > 0 and isinstance(tr["qty"],int)
        assert tr["modeled_fill_price"] == pytest.approx(
            tr["reference_price"] * (1.001 if tr["side"]=="BUY" else .999))
        assert tr["fee"] == pytest.approx(tr["gross_notional"] * .0002)
        assert tr["modeled_slippage_cost"] == pytest.approx(
            tr["qty"] * abs(tr["modeled_fill_price"]-tr["reference_price"]))
    return row, trades


@pytest.mark.parametrize("old,new", TRANSITIONS,
                         ids=[old+"-to-"+new for old,new in TRANSITIONS])
def test_all_sixteen_cash_and_leverage_transitions_replayed_independently(old,new):
    state=new_state()
    prev=signal("2026-10-07",old,action="EXPOSURE_CHANGE")
    row0,trades0=step(state,prev,market("2026-10-08"),bootstrap=True)
    current=signal("2026-10-08",new,
                   action="NO_CHANGE" if old==new else "EXPOSURE_CHANGE")
    row1,trades1=step(state,current,market("2026-10-09"))
    if old==new:
        assert trades1==[], "NO_CHANGE must not rebalance tiny rounding noise"
    if old=="CASH" and new!="CASH":
        assert all(t["side"]=="BUY" for t in trades1)
        assert trades1
    if old!="CASH" and new=="CASH":
        assert trades1 and all(t["side"]=="SELL" for t in trades1)
        assert state["shares"]=={"QQQ":0,"TQQQ":0}
    if old=="L3" and new=="L1":
        assert [(t["symbol"],t["side"]) for t in trades1]==[
            ("TQQQ","SELL"),("QQQ","BUY")]
    if old=="L1" and new=="L3":
        assert [(t["symbol"],t["side"]) for t in trades1]==[
            ("QQQ","SELL"),("TQQQ","BUY")]
    if new=="CASH":
        assert state["shares"]=={"QQQ":0,"TQQQ":0}
    proof=independent_accounting(
        [row0,row1], trades0+trades1,
        {prev["latest"]["asof_date"]:prev,current["latest"]["asof_date"]:current})
    assert proof["status"]=="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS",proof
    assert proof["verified_paper_sessions"]==2
    assert proof["broker_fills_observed"] is False
    assert proof["live_trading_authorized"] is False


def _files(folder: Path):
    return {
        "state":folder/"state.json",
        "trades":folder/"trades.csv",
        "ledger":folder/"ledger.csv",
        "latest":folder/"latest.md",
        "snapshot":folder/"latest_session.json",
    }


def _csv(path):
    with path.open(newline="",encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_twenty_day_forced_order_lifecycle_persists_and_audits_every_session(
        tmp_path, monkeypatch):
    folder=tmp_path/"isolated-synthetic-paper"
    paths=_files(folder)
    monkeypatch.setattr(paper_portfolio,"STATE_DIR",folder)
    monkeypatch.setattr(paper_portfolio,"STATE_PATH",paths["state"])
    monkeypatch.setattr(paper_portfolio,"TRADES_PATH",paths["trades"])
    monkeypatch.setattr(paper_portfolio,"LEDGER_PATH",paths["ledger"])
    monkeypatch.setattr(paper_portfolio,"LATEST_MD_PATH",paths["latest"])
    monkeypatch.setattr(paper_portfolio,"GAPS_PATH",folder/"evidence_gaps.csv")
    days=[x.date().isoformat() for x in
          xcals.get_calendar("XNYS").sessions_in_range("2026-10-08","2026-11-05")]
    # Includes multiple complete round-trips BUY -> SELL -> BUY, a low-risk
    # QQQ/TQQQ switch, defense entry/exit, and consecutive NO_CHANGE sessions.
    targets=("CASH","L3","L1","L2","L3","L3","CASH","CASH",
             "L1","L3","L2","L1","CASH","L2","L3","CASH",
             "L1","L1","L3","CASH")
    assert len(days)>=len(targets)
    snapshots={}
    outcomes=[]
    for i,target in enumerate(targets):
        day=days[i]
        previous=xcals.get_calendar("XNYS").previous_session(day).date().isoformat()
        action="NO_CHANGE" if i and target==targets[i-1] else "EXPOSURE_CHANGE"
        prior=signal(previous,target,action=action)
        current=signal(day,target)
        snapshots[previous]=prior
        path0=tmp_path/"current.json"
        path1=tmp_path/"previous.json"
        path0.write_text(json.dumps(current))
        path1.write_text(json.dumps(prior))
        monkeypatch.setattr(paper_portfolio,"fetch_execution_market",
                            lambda p,c,day=day: market(day))
        res=paper_portfolio.reconcile(str(path0),str(path1))
        assert res["paper_status"]=="OK",res
        assert res["paper_updated"]=="true"
        assert res["paper_session"]==day
        assert recover_paper(paths) is None
        assert not list((folder/".transactions").glob("*.json"))
        rows=_csv(paths["ledger"])
        trades=_csv(paths["trades"]) if paths["trades"].exists() else []
        assert len(rows)==i+1
        assert len(set(x["session_date"] for x in rows))==len(rows)
        assert rows[-1]["target_defense"]==str(target=="CASH")
        assert float(rows[-1]["cash"])>=0
        assert rows[-1]["trade_count_session"]==res["paper_trades"]
        if i and target==targets[i-1]:
            assert res["paper_trades"]=="0"
        if i and targets[i-1]=="L3" and target=="L1":
            last=[t for t in trades if t["execution_session"]==day]
            assert [(t["symbol"],t["side"]) for t in last]==[
                ("TQQQ","SELL"),("QQQ","BUY")]
        before=(paths["trades"].read_bytes() if paths["trades"].exists() else None,
                paths["ledger"].read_bytes(),paths["state"].read_bytes())
        repeat=paper_portfolio.reconcile(str(path0),str(path1))
        assert repeat["paper_updated"]=="false"
        assert repeat["paper_status"]=="SIGNAL_ALREADY_RECONCILED"
        after=(paths["trades"].read_bytes() if paths["trades"].exists() else None,
               paths["ledger"].read_bytes(),paths["state"].read_bytes())
        assert before==after,"retry must not double-order or duplicate receipts"
        proof=independent_accounting(rows,trades,snapshots)
        assert proof["status"]=="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS",proof
        assert proof["modeled_trades"]==len(trades)
        outcomes.append((target,res["paper_trades"]))
    assert any(int(n)>0 for _,n in outcomes)
    assert any(int(n)==0 for _,n in outcomes)
    assert _csv(paths["ledger"])[-1]["target_defense"]=="True"
    assert int(_csv(paths["ledger"])[-1]["qqq_shares"])==0
    assert int(_csv(paths["ledger"])[-1]["tqqq_shares"])==0


def test_sale_proceeds_fund_same_session_new_purchase_with_sell_first():
    state=new_state()
    step(state,signal("2026-10-07","L3"),market("2026-10-08"),bootstrap=True)
    before_cash=state["cash"]
    row,trades=step(state,signal("2026-10-08","L1",action="EXPOSURE_CHANGE"),
                    market("2026-10-09"))
    assert len(trades)==2
    assert trades[0]["side"]=="SELL" and trades[0]["time_et"]=="09:31"
    assert trades[1]["side"]=="BUY" and trades[1]["time_et"]=="09:32"
    assert trades[1]["gross_notional"]>before_cash
    assert row["qqq_shares"]>0 and row["tqqq_shares"]>0


def test_buy_is_cash_capped_without_negative_balance_or_partial_fake_fill():
    state=new_state()
    state["cash"]=101.0
    trade=_trade(state,"QQQ","BUY",1000,100.,"09:32","2026-10-08","2026-10-07")
    assert trade is not None and trade["qty"]==1
    assert state["shares"]["QQQ"]==1 and state["cash"]>=0
    again=_trade(state,"QQQ","BUY",10,100.,"09:32","2026-10-08","2026-10-07")
    assert again is None
    assert state["trade_count"]==1


def test_sells_never_exceed_owned_shares():
    state=new_state()
    state["shares"]["TQQQ"]=3
    tr=_trade(state,"TQQQ","SELL",100,50.,"09:31","2026-10-08","2026-10-07")
    assert tr["qty"]==3
    assert state["shares"]["TQQQ"]==0
    assert _trade(state,"TQQQ","SELL",10,50.,"09:31",
                  "2026-10-08","2026-10-07") is None


@pytest.mark.parametrize("bad",[
    {"qqq_weight":.8,"tqqq_weight":.8},
    {"qqq_weight":-.01,"tqqq_weight":0},
    {"qqq_weight":float("nan"),"tqqq_weight":0},
    {"qqq_weight":float("inf"),"tqqq_weight":0},
])
def test_invalid_signal_weights_never_trade(bad):
    state=new_state()
    s=signal("2026-10-07","L3")
    s["latest"].update(bad)
    with pytest.raises(PaperIntegrityError,match="INVALID_FROZEN_PAPER_TARGET_WEIGHTS"):
        rebalance_if_required(state,s,market("2026-10-08"),bootstrap=True)
    assert state["trade_count"]==0
    assert state["cash"]==100000.


def test_no_change_with_real_holdings_mismatch_still_places_corrective_orders():
    state=new_state()
    step(state,signal("2026-10-07","L3"),market("2026-10-08"),bootstrap=True)
    state["shares"]["TQQQ"]=0
    state["cash"]=100000.
    row,trades=step(state,signal("2026-10-08","L3",action="NO_CHANGE"),
                    market("2026-10-09"))
    assert trades and trades[0]["side"]=="BUY"
    assert row["paper_action"]=="RECONCILE_ACTUAL_HOLDINGS"


def test_vendor_0932_price_gap_does_not_buy_more_than_cash():
    state=new_state()
    row,trades=step(state,signal("2026-10-07","L3"),
                    market("2026-10-08",t31=50.,t32=80.,tclose=80.),
                    bootstrap=True)
    assert all(t["side"]=="BUY" for t in trades)
    assert state["cash"]>=0
    assert row["target_tracking_gap_after"]<.01


def test_company_dividend_is_logged_in_model_state_and_ledger():
    state=new_state()
    step(state,signal("2026-10-07","L1"),market("2026-10-08"),bootstrap=True)
    prior_cash=state["cash"]
    prior_shares=state["shares"]["QQQ"]
    row,trades=step(state,signal("2026-10-08","L1",action="NO_CHANGE"),
                    market("2026-10-09",dividend={"QQQ":.25,"TQQQ":0.}))
    assert row["dividends_credited_session"]==pytest.approx(prior_shares*.25)
    assert state["cumulative_dividends"]==pytest.approx(prior_shares*.25)
    assert row["cash"]==pytest.approx(
        prior_cash+prior_shares*.25+
        sum((1 if x["side"]=="SELL" else -1)*x["gross_notional"]-x["fee"]
            for x in trades))


def test_fractional_stock_split_fails_before_any_fabricated_inventory():
    state=new_state()
    state["shares"]["QQQ"]=3
    with pytest.raises(PaperIntegrityError,match="FRACTIONAL_SHARES_FROM_SPLIT"):
        _apply_corporate_actions(
            state,market("2026-10-08",split={"QQQ":1.5,"TQQQ":0.}))
    assert state["shares"]["QQQ"]==3


def test_independent_replay_rejects_forged_trade_and_ledger():
    state=new_state()
    s=signal("2026-10-07","L3")
    row,trades=step(state,s,market("2026-10-08"),bootstrap=True)
    good=independent_accounting([row],trades,{"2026-10-07":s})
    assert good["status"]=="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"
    forged=deepcopy(trades)
    forged[0]["fee"]=0.0
    audit=independent_accounting([row],forged,{"2026-10-07":s})
    assert audit["status"]=="FAIL"
    assert "INVALID_TRADE_FEE_NOTIONAL:2026-10-08" in audit["errors"]
    forged_row=deepcopy(row)
    forged_row["cash"]=float(row["cash"])+1000
    audit=independent_accounting([forged_row],trades,{"2026-10-07":s})
    assert audit["status"]=="FAIL"
    assert "INCEPTION_CASH_INVALID:2026-10-08" in audit["errors"]


def test_late_signal_is_refused_before_paper_reconcile():
    s=signal("2026-10-07","L3")
    s["generated_at_utc"]="2026-10-08T15:00:00Z"
    assert paper_portfolio._signal_precedes_session(s,"2026-10-08") is False


def test_actual_cash_and_source_are_never_broker_fills():
    state=new_state()
    s=signal("2026-10-07","L2")
    row,trades=step(state,s,market("2026-10-08"),bootstrap=True)
    proof=independent_accounting([row],trades,{"2026-10-07":s})
    assert proof["broker_fills_observed"] is False
    assert proof["quote_bid_ask_proven"] is False
    assert proof["independent_vendor_close_proven"] is False
