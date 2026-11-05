"""SL-50 receipt replay rejects fabricated SHA and unverified FX evidence."""
import hashlib
import json
import pytest

from research.paper_tax_receipts import examine


def example():
    row={"session_date":"2026-11-02","equity":10500,
         "qqq_shares":0,"tqqq_shares":10,"trade_count_session":0}
    buy={"execution_session":"2026-10-30","signal_date":"2026-10-29",
         "time_et":"09:32","side":"BUY","symbol":"TQQQ","qty":10,
         "modeled_fill_price":100,"fee":0.2}
    data={"session":"2026-11-02","broker_fills_observed":False,
          "broker_orders_authorized":False,"row":row,
          "history":{"ledger":[{"session_date":"2026-10-30","trade_count_session":1},
                               row],"trades":[buy]}}
    raw=json.dumps(data,sort_keys=True).encode()
    return raw,hashlib.sha256(raw).hexdigest()


def test_history_replays_without_fictitious_tax_on_unrealized_gain():
    raw,sha=example()
    x=examine(raw,sha,{"2026-10-30":"3.5"})
    assert x["status"]=="RESEARCH_ONLY_TAX_RECEIPT_REPLAY"
    assert x["tax"]["tax_assessed_ils"]=="0"
    assert x["gross_paper_nav_usd"]==x["hypothetical_after_tax_value_usd"]


def test_refuse_unverified_receipt_and_missing_trade_fx():
    raw,sha=example()
    with pytest.raises(ValueError,match="SHA"):
        examine(raw,"0"*64,{"2026-10-30":"3.5"})
    with pytest.raises(ValueError,match="FX"):
        examine(raw,sha,{})


def test_refuse_holdings_mismatch_and_claimed_broker_orders():
    raw,sha=example()
    x=json.loads(raw)
    x["row"]["tqqq_shares"]=9
    altered=json.dumps(x,sort_keys=True).encode()
    with pytest.raises(ValueError,match="QTY"):
        examine(altered,hashlib.sha256(altered).hexdigest(),{"2026-10-30":"3.5"})
    x["broker_orders_authorized"]=True
    altered=json.dumps(x,sort_keys=True).encode()
    with pytest.raises(ValueError,match="NOT_SAFE"):
        examine(altered,hashlib.sha256(altered).hexdigest(),{"2026-10-30":"3.5"})
