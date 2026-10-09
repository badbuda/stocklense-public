"""Regression: real StockLens level schema and actual paper holdings on NO_CHANGE."""
import ast
import math
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import pytest
from stocklens.core import LEVEL_LEVERAGE,TARGET_INVESTED_FRACTION,weights_for_leverage
from stocklens.paper import SessionMarket,PaperIntegrityError,new_state,rebalance_if_required,mark_session

NOW=datetime(2026,10,9,9,10,tzinfo=timezone.utc)
DAY="2026-10-08"

def aws_validate():
    text=Path("infra/aws/paper-signal-journal.yaml").read_text()
    part=text.split("  ShadowLambda:")[1].split("  PaperEvidenceLogs:")[0]
    source="\n".join(line[10:] if line.startswith("          ") else line
                    for line in part.split("ZipFile: |\n")[1].splitlines())
    tree=ast.parse(source)
    fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="validate")
    ns={"math":math,"datetime":datetime,"time":time,"timedelta":timedelta,"timezone":timezone,"ZoneInfo":ZoneInfo}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"shadow-lambda-validate","exec"),ns)
    return ns["validate"]

def signal(level, defense=False):
    leverage=0.0 if defense else LEVEL_LEVERAGE[level]
    q,t=weights_for_leverage(leverage)
    return {"version":"8.0.2-shadow-completed-session-guard",
            "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "signal_source":"QQQ_ADJUSTED_DAILY_CLOSE",
            "execution_plan":{"broker_actions_enabled":False},
            "generated_at_utc":"2026-10-09T00:00:00Z",
            "latest":{"asof_date":DAY,"level":level,"defense_active":defense,
                      "target_leverage":leverage,
                      "qqq_weight":q*TARGET_INVESTED_FRACTION,
                      "tqqq_weight":t*TARGET_INVESTED_FRACTION}}

@pytest.mark.parametrize("level",[1,2,3])
@pytest.mark.parametrize("defense",[False,True])
def test_lambda_accepts_all_valid_levels_including_defense(level,defense):
    assert aws_validate()(signal(level,defense),NOW)==DAY

@pytest.mark.parametrize("bad_level",[0,1.25,4,True])
def test_lambda_rejects_leverage_or_invalid_level(bad_level):
    x=signal(1);x["latest"]["level"]=bad_level
    with pytest.raises(ValueError,match="FROZEN_MODEL_LEVEL_INVALID"):
        aws_validate()(x,NOW)

def test_lambda_rejects_wrong_leverage_for_level():
    x=signal(1);x["latest"]["target_leverage"]=1.
    with pytest.raises(ValueError,match="FROZEN_MODEL_LEVERAGE_MISMATCH"):
        aws_validate()(x,NOW)

def market():
    return SessionMarket("2026-10-08",
        {"QQQ":100.0,"TQQQ":50.0},{"QQQ":100.0,"TQQQ":50.0},
        {"QQQ":100.0,"TQQQ":50.0},{"QQQ":0.0,"TQQQ":0.0},{"QQQ":0.0,"TQQQ":0.0})

def paper_signal(qqq=0.,tqqq=.985,action="NO_CHANGE"):
    return {"action":action,"latest":{"asof_date":"2026-10-07",
        "level":3,"defense_active":False,"target_leverage":3.0,
        "qqq_weight":qqq,"tqqq_weight":tqqq}}

def test_no_change_recovers_missed_bootstrap_when_cash_is_off_target():
    state=new_state();state["last_executed_signal_date"]="2026-10-06"
    ts=rebalance_if_required(state,paper_signal(),market(),bootstrap=False)
    assert len(ts)==1 and ts[0]["side"]=="BUY" and ts[0]["time_et"]=="09:32"
    assert state["shares"]["TQQQ"]>0
    row=mark_session(state,paper_signal(),market(),ts,{"dividends_credited":0.0},False)
    assert row["paper_action"]=="RECONCILE_ACTUAL_HOLDINGS"
    assert row["target_tracking_gap_after"]<.01

def test_no_change_rebalances_stale_incorrect_qqq_position():
    state=new_state();state["cash"]=10000.;state["shares"]["QQQ"]=900
    state["last_executed_signal_date"]="2026-10-06"
    ts=rebalance_if_required(state,paper_signal(),market(),False)
    assert any(t["symbol"]=="QQQ" and t["side"]=="SELL" and t["time_et"]=="09:31" for t in ts)
    assert any(t["symbol"]=="TQQQ" and t["side"]=="BUY" and t["time_et"]=="09:32" for t in ts)

def test_no_change_within_band_does_not_trade():
    state=new_state();state["shares"]["TQQQ"]=1970;state["cash"]=1500.
    assert rebalance_if_required(state,paper_signal(),market(),False)==[]

def test_no_change_in_defense_sells_actual_holding():
    state=new_state();state["shares"]["TQQQ"]=1000;state["cash"]=1000.
    ts=rebalance_if_required(state,paper_signal(0.,0.),market(),False)
    assert state["shares"]["TQQQ"]==0 and len(ts)==1 and ts[0]["side"]=="SELL"

def test_invalid_frozen_target_fails_before_paper_trades():
    state=new_state()
    with pytest.raises(PaperIntegrityError,match="INVALID_FROZEN_PAPER_TARGET_WEIGHTS"):
        rebalance_if_required(state,paper_signal(.8,.6),market(),True)
    assert state["trade_count"]==0

def test_unreconciled_position_fails_closed_on_mark():
    state=new_state();state["last_executed_signal_date"]="2026-10-06"
    with pytest.raises(PaperIntegrityError,match="PAPER_POST_REBALANCE_TARGET_MISMATCH"):
        mark_session(state,paper_signal(),market(),[],{"dividends_credited":0.0},False)

def test_lambda_rejects_same_ny_calendar_day_when_archiving_yesterday():
    x=signal(3);x["latest"]["asof_date"]="2026-10-09"
    with pytest.raises(RuntimeError,match="STALE_COMPLETED_SESSION"):
        aws_validate()(x,NOW)

def test_lambda_rejects_early_archive_before_ny_four_am():
    with pytest.raises(RuntimeError,match="NOT_COMPLETED_US_MARKET_SESSION"):
        aws_validate()(signal(3),datetime(2026,10,9,6,59,tzinfo=timezone.utc))

def test_lambda_handles_est_winter_prior_session():
    x=signal(3)
    x["generated_at_utc"]="2026-12-09T00:00:00Z"
    x["latest"]["asof_date"]="2026-12-08"
    assert aws_validate()(x,datetime(2026,12,9,9,10,tzinfo=timezone.utc))=="2026-12-08"
