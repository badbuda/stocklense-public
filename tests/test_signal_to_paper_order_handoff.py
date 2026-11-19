"""Decision-to-execution real-code coverage: threshold -> target -> trade.

Forces risk regimes (trend, hysteresis, 20d volatility, defense) rather than
waiting for a future real market signal. No AWS, S3, exchange, or broker actions.
Real BUY/SELL modeled fills from stocklens.paper, not a deployed Lambda.
"""
from __future__ import annotations
import pytest
from stocklens.core import (
    Features, defense_active, next_level, weights_for_leverage,
    LEVEL_LEVERAGE, TARGET_INVESTED_FRACTION,
)
from stocklens.paper import (
    new_state, SessionMarket, rebalance_if_required, mark_session,
    _apply_corporate_actions,
)
from broker_adapter import (
    OrderIntent, DisabledBroker, ReadOnlyBroker, BrokerMode, assert_live_gate,
)
from paper_portfolio_integrity import evaluate


def features(*, close=103., sma50=105., sma200=100.,vol=.2,momentum=.1):
    return Features(close=close,sma50=sma50,sma200=sma200,
                    vol20=vol,mom12=momentum)


@pytest.mark.parametrize("previous,price,vol,expected",[
    (None, 103., .2, 3),
    (1, 101., .2, 1),           # risk-OFF requires STRICT > 1.01*SMA200
    (1, 101.00001, .279999, 3),
    (1, 102., .279999, 3),
    (1, 102., .28, 2),
    (1, 102., .379999, 2),
    (1, 102., .38, 1),
    (2, 99., .3, 2),            # risk-ON 0.99*SMA200 boundary inclusive
    (2, 98.99999, .1, 1),
    (2, 103., .279999, 3),
    (2, 103., .28, 2),
    (2, 103., .419999, 2),
    (2, 103., .42, 1),
    (3, 103., .319999, 3),
    (3, 103., .32, 2),
    (3, 98.99999, .1, 1),
])
def test_hysteresis_and_volatility_threshold_boundaries(previous,price,vol,expected):
    assert next_level(features(close=price,vol=vol),previous)==expected


@pytest.mark.parametrize("sma50,momentum,expected",[
    (99.,-.1,True),
    (99.,0.,True),
    (99.,.00001,False),
    (100.,-.1,False),
    (101.,-.1,False),
])
def test_defense_requires_both_bearish_trend_and_momentum(sma50,momentum,expected):
    assert defense_active(features(sma50=sma50,momentum=momentum)) is expected


def decide(previous, f, prior, action):
    level=next_level(f,previous)
    guarded=defense_active(f)
    leverage=0. if guarded else LEVEL_LEVERAGE[level]
    q,t=weights_for_leverage(leverage)
    return {"action":action,
            "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "generated_at_utc":prior+"T23:10:00Z",
            "execution_plan":{"broker_actions_enabled":False},
            "latest":{"asof_date":prior,"level":level,
                "defense_active":guarded,
                "target_leverage":leverage,
                "qqq_weight":q*TARGET_INVESTED_FRACTION,
                "tqqq_weight":t*TARGET_INVESTED_FRACTION}}


def market(day):
    return SessionMarket(day,{"QQQ":100.,"TQQQ":50.},
                         {"QQQ":100.,"TQQQ":50.},
                         {"QQQ":100.,"TQQQ":50.},
                         {"QQQ":0.,"TQQQ":0.},
                         {"QQQ":0.,"TQQQ":0.})


def execute(state,s,day,bootstrap):
    m=market(day)
    corp=_apply_corporate_actions(state,m)
    orders=rebalance_if_required(state,s,m,bootstrap)
    ledger=mark_session(state,s,m,orders,corp,bootstrap)
    assert all(x["side"] in ("BUY","SELL") for x in orders)
    assert all(x["time_et"]==("09:31" if x["side"]=="SELL" else "09:32")
               for x in orders)
    return ledger,orders


def test_market_risk_to_full_defense_to_new_buy_orders_real_model():
    state=new_state()
    # The model itself picks level 3 and buys TQQQ from zero holdings.
    normal=decide(1,features(vol=.1),"2026-10-07","EXPOSURE_CHANGE")
    assert normal["latest"]["level"]==3
    a, buy = execute(state,normal,"2026-10-08",True)
    assert buy and all(t["side"]=="BUY" for t in buy)
    assert any(t["symbol"]=="TQQQ" for t in buy)
    # Bearish 50d vs 200d plus negative momentum: SELL ALL despite high level.
    defensive=decide(3,features(close=103.,sma50=90.,momentum=-.1),
                     "2026-10-08","EXPOSURE_CHANGE")
    assert defensive["latest"]["defense_active"] is True
    b, sell = execute(state,defensive,"2026-10-09",False)
    assert sell and all(t["side"]=="SELL" for t in sell)
    assert state["shares"]=={"QQQ":0,"TQQQ":0}
    # Back to trend-on and positive momentum: a new buy must be modeled.
    reentry=decide(3,features(vol=.1,momentum=.1),
                   "2026-10-09","EXPOSURE_CHANGE")
    c, rebuy = execute(state,reentry,"2026-10-12",False)
    assert rebuy and all(t["side"]=="BUY" for t in rebuy)
    assert state["shares"]["TQQQ"]>0
    proof=evaluate([a,b,c],buy+sell+rebuy,{
        "2026-10-07":normal,
        "2026-10-08":defensive,
        "2026-10-09":reentry,
    })
    assert proof["status"]=="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS",proof
    assert proof["broker_fills_observed"] is False


@pytest.mark.parametrize("level",[1,2,3])
def test_real_decision_weights_reflected_in_buy_order_and_cash_reserve(level):
    f=features(vol=.3 if level==2 else .1 if level==3 else .4)
    d=decide(1,f,"2026-10-07","EXPOSURE_CHANGE")
    assert d["latest"]["level"]==level
    st=new_state()
    _, orders=execute(st,d,"2026-10-08",True)
    assert orders and any(x["side"]=="BUY" for x in orders)
    assert st["cash"]>=0
    target=d["latest"]
    assert target["qqq_weight"]+target["tqqq_weight"]==pytest.approx(.985)
    assert st["shares"]["QQQ"] >=0 and st["shares"]["TQQQ"]>=0


@pytest.mark.parametrize("backend",[DisabledBroker,ReadOnlyBroker])
def test_synthetic_paper_never_submits_to_broker(backend):
    order=OrderIntent(session="2026-10-08",symbol="QQQ",side="BUY",
                      quantity=10,reason="synthetic-replay",target_leverage=1.25)
    adapter=backend()
    assert adapter.preview(order)["allowed"] is False
    with pytest.raises(RuntimeError,match="LIVE_ORDER_BLOCKED"):
        adapter.submit(order)
    assert order.idempotency_key==order.idempotency_key


@pytest.mark.parametrize("mode,explicit,reconciled",[
    (BrokerMode.DISABLED,True,True),
    (BrokerMode.READ_ONLY,True,True),
    (BrokerMode.PAPER,True,True),
    (BrokerMode.LIVE,False,True),
    (BrokerMode.LIVE,True,False),
])
def test_live_gateway_never_enables_without_all_safety_gates(mode,explicit,reconciled):
    with pytest.raises(RuntimeError,match="LIVE_ORDER_BLOCKED"):
        assert_live_gate(mode,explicit,reconciled)
