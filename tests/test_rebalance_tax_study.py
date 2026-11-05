"""SL-51 scenarios: exact target shares, guarded risk exits and tax drag."""
import pytest
from decimal import Decimal
from research.rebalance_tax_study import replay, compare, target, monthly_broker_tax_projection
from stocklens.tax_research import TaxBook


def session(day, lev, action="REBALANCE_NEXT_SESSION", q=100, t=100, fx=3.5):
    return {"date": day,"leverage":lev,"action":action,
            "qqq_0931":q,"qqq_0932":q,"qqq_close":q,
            "tqqq_0931":t,"tqqq_0932":t,"tqqq_close":t,
            "fx_ils_per_usd":fx}


def test_frozen_weights_and_invested_fraction():
    assert target(3.0)=={"QQQ":0.0,"TQQQ":0.985}
    assert target(2.0)=={"QQQ":0.4925,"TQQQ":0.4925}
    assert target(0.0)=={"QQQ":0.0,"TQQQ":0.0}
    assert target(1.25)["TQQQ"]==pytest.approx(0.123125)
    assert target(1.25)["QQQ"]==pytest.approx(0.861875)


def test_level_change_sells_only_excess_not_entire_etf():
    a=[session("2026-10-30",3.0),session("2026-11-02",2.0)]
    out=replay(a)
    assert out["ledger"][0]["shares"]["TQQQ"] > 0
    after=out["ledger"][1]
    assert after["shares"]["TQQQ"] > 0
    assert after["shares"]["QQQ"] > 0
    assert len([t for t in after["trades"] if t["side"]=="SELL"])==1
    assert after["trades"][0]["qty"] < out["ledger"][0]["shares"]["TQQQ"]
    assert out["scenario"]["immediate_tax_withholding"] is False


def test_cash_defense_liquidates_both_instruments():
    a=[session("2026-10-30",2),session("2026-11-02",0,"ENTER_CASH_NEXT_SESSION")]
    out=replay(a)
    assert out["ledger"][-1]["shares"]=={"QQQ":0,"TQQQ":0}
    assert out["ledger"][-1]["trades"]
    assert out["ledger"][-1]["cash_usd"] > 0


def test_no_change_noise_vs_wider_band():
    a=[session("2026-10-30",2),session("2026-11-02",2,"NO_CHANGE",q=98.5,t=101.5)]
    baseline=replay(a,0.005)
    wider=replay(a,0.02)
    assert baseline["ledger"][1]["skipped"] is False
    assert wider["ledger"][1]["skipped"] is True
    assert baseline["counts"]["BUY"]+baseline["counts"]["SELL"] > wider["counts"]["BUY"]+wider["counts"]["SELL"]


def test_immediate_tax_reduces_buying_power_after_realized_profit():
    a=[session("2026-10-30",3),session("2026-11-02",2,t=120)]
    gross=replay(a)
    withheld=replay(a,immediate_tax_withholding=True)
    assert Decimal(gross["estimated_tax_assessed_ils"]) > 0
    assert withheld["estimated_withheld_usd"] > 0
    assert withheld["nav_usd"] < gross["nav_usd"]
    assert withheld["ledger"][-1]["shares"]["QQQ"] <= gross["ledger"][-1]["shares"]["QQQ"]


def test_comparison_never_changes_source_events_and_has_four_cases():
    a=[session("2026-10-30",3),session("2026-11-02",2)]
    saved=repr(a)
    result=compare(a)
    assert repr(a)==saved
    assert len(result["comparison"])==4
    assert all(v["model"]=="RESEARCH_NOT_LIVE" for v in result["comparison"].values())


def test_unsorted_and_missing_fx_fail_closed():
    a=[session("2026-10-30",3),session("2026-10-30",2)]
    with pytest.raises(ValueError,match="UNSORTED"):
        replay(a)
    e=session("2026-10-30",3,fx=0)
    with pytest.raises(ValueError,match="FX"):
        replay([e])


def test_monthly_broker_projection_credits_later_loss_in_same_year():
    book=TaxBook()
    book.buy("2026-10-30","TQQQ",10,100,0,3.5)
    book.sell("2026-11-02","TQQQ",5,120,0,3.5)
    book.sell("2026-12-02","TQQQ",5,80,0,3.5)
    settlement=monthly_broker_tax_projection(book.events)["settlements"]
    assert len(settlement)==2
    assert settlement[0]["month"]=="2026-11"
    assert settlement[0]["estimated_settlement_ils"]==87.5
    assert settlement[1]["estimated_settlement_ils"]==-87.5
    assert settlement[1]["year_to_date_liability_ils"]==0


def test_monthly_netting_does_not_claim_cross_year_refund():
    book=TaxBook()
    book.buy("2026-10-30","TQQQ",10,100,0,3.5)
    book.sell("2026-12-02","TQQQ",5,120,0,3.5)
    book.sell("2027-01-04","TQQQ",5,80,0,3.5)
    rows=monthly_broker_tax_projection(book.events)["settlements"]
    assert rows[0]["estimated_settlement_ils"]==87.5
    assert rows[1]["estimated_settlement_ils"]==0
