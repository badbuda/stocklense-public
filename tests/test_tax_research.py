"""SL-50 tax research invariants; no live trading or source provider."""
from decimal import Decimal
import pytest
from stocklens.tax_research import TaxBook


def test_partial_fifo_profit_and_fee_basis():
    book = TaxBook()
    book.buy("2026-01-05", "TQQQ", 10, 80, 2, 3.5)
    book.buy("2026-02-05", "TQQQ", 10, 110, 0, 3.7)
    x = book.sell("2026-03-05", "TQQQ", 12, 120, 1.2, 3.6)
    assert book.quantity("TQQQ") == 8
    assert x["fifo_consumed"] == [
        {"date":"2026-01-05","qty":10,"basis_usd":"80.2"},
        {"date":"2026-02-05","qty":2,"basis_usd":"110"},
    ]
    assert Decimal(x["net_proceeds_usd"]) == Decimal("1438.8")
    assert Decimal(x["realized_usd"]) == Decimal("416.8")
    assert Decimal(x["estimated_incremental_tax_ils"]) > 0


def test_loss_offsets_future_gain_but_no_retroactive_refund():
    book = TaxBook()
    book.buy("2026-01-05", "TQQQ", 10, 100, 0, 3.5)
    loss = book.sell("2026-01-06", "TQQQ", 10, 80, 0, 3.5)
    assert Decimal(loss["eligible_loss_ils"]) == Decimal("700")
    assert Decimal(loss["estimated_incremental_tax_ils"]) == 0
    book.buy("2026-02-02", "TQQQ", 10, 100, 0, 3.5)
    gain = book.sell("2026-02-03", "TQQQ", 10, 120, 0, 3.5)
    assert Decimal(gain["loss_offset_ils"]) == Decimal("700")
    assert Decimal(gain["estimated_incremental_tax_ils"]) == 0
    assert Decimal(book.summary()["unused_loss_pool_ils"]) == 0


def test_pure_fx_loss_is_not_deductible():
    book = TaxBook()
    book.buy("2026-01-02", "QQQ", 1, 100, 0, 4.0)
    row = book.sell("2026-01-03", "QQQ", 1, 100, 0, 3.0)
    assert Decimal(row["nominal_ils"]) == -100
    assert Decimal(row["fx_indexed_ils"]) == 0
    assert Decimal(row["eligible_loss_ils"]) == 0


def test_fx_indexed_taxable_gain_is_not_dollar_gain_times_buy_fx():
    book = TaxBook()
    book.buy("2026-01-02", "QQQ", 1, 100, 0, 3.5)
    row = book.sell("2026-01-03", "QQQ", 1, 120, 0, 4.0)
    assert Decimal(row["eligible_gain_ils"]) == 80
    assert Decimal(row["estimated_incremental_tax_ils"]) == 20


def test_no_tax_on_buy_and_fee_reduces_taxable_profit():
    b=TaxBook()
    b.buy("2026-01-02","QQQ",2,100,2,3)
    assert b.summary()["tax_assessed_ils"]=="0"
    row=b.sell("2026-01-03","QQQ",2,110,2,3)
    assert Decimal(row["realized_usd"])==Decimal("16")
    assert Decimal(row["estimated_incremental_tax_ils"])==Decimal("12")


def test_reject_missing_lots_or_invalid_fx():
    b=TaxBook()
    with pytest.raises(ValueError):
        b.sell("2026-01-01","TQQQ",1,50,0,3.5)
    with pytest.raises(ValueError):
        b.buy("2026-01-02","TQQQ",1,50,0,0)
    with pytest.raises(ValueError):
        b.buy("2026-01-02","TQQQ",0,50,0,3.5)


def test_different_years_not_claimed_as_tax_return():
    b=TaxBook(opening_losses_ils="100")
    b.buy("2025-12-30","QQQ",1,100,0,3.5)
    row=b.sell("2026-01-02","QQQ",1,120,0,3.5)
    assert Decimal(row["loss_offset_ils"])==70
    assert b.summary()["mode"]=="RESEARCH_PRETAX_PAPER_UNCHANGED"
    assert b.summary()["tax_was_withheld"] is False


def test_split_preserves_total_fifo_basis_and_position():
    b=TaxBook()
    b.buy("2026-01-02","TQQQ",10,100,2,3.5)
    original=Decimal("1002")
    b.split("2026-01-03","TQQQ",2,1)
    assert b.quantity("TQQQ")==20
    assert b.lots["TQQQ"][0].basis_usd*20==original
    x=b.sell("2026-01-04","TQQQ",10,60,0,3.5)
    assert Decimal(x["realized_usd"])==Decimal("99")


def test_split_fractional_and_lookahead_rejected_without_mutation():
    b=TaxBook()
    b.buy("2026-01-03","QQQ",1,100,0,3.5)
    with pytest.raises(ValueError,match="FRACTIONAL"):
        b.split("2026-01-04","QQQ",1,2)
    assert b.quantity("QQQ")==1
    with pytest.raises(ValueError,match="NONCHRONOLOGICAL"):
        b.sell("2026-01-02","QQQ",1,101,0,3.5)
    assert b.quantity("QQQ")==1
