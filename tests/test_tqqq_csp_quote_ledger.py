"""Synthetic unit fixtures for quote-gated CSP ledger. NOT historical returns."""
import csv
from decimal import Decimal as D
import tempfile
import unittest
from pathlib import Path

from research.tqqq_cash_secured_options_ledger import Quote, CashSecuredPutLedger, import_cboe_csv


def quote(date="2025-10-21", expiry="2025-11-21", strike="70",
          bid="2.0", ask="2.1", right="P", root="TQQQ"):
    return Quote(
        underlying="TQQQ", quote_date=date, expiration=expiry,
        strike=D(strike), right=right, bid=D(bid), ask=D(ask),
        bid_size=100, ask_size=100, open_interest=300,
        multiplier=100, quote_clock="15:45:00",
        contract_adjustment_verified=True, root=root
    )


class TestTQQQOptionAccounting(unittest.TestCase):
    def test_cash_gate_and_caps(self):
        book=CashSecuredPutLedger(D("100000"))
        with self.assertRaisesRegex(ValueError,"STOCKLENS_CASH"):
            book.sell_put(quote(),1,stocklens_target=0,mark_underlying=D("80"))
        self.assertEqual(book.cash,D("100000"))
        with self.assertRaisesRegex(ValueError,"MAX_CASH_SLEEVE"):
            book.sell_put(quote(),3,stocklens_target=3,mark_underlying=D("80"))
        self.assertEqual(book.cash,D("100000"))
        credit=book.sell_put(quote(),2,stocklens_target=2,mark_underlying=D("80"))
        self.assertEqual(credit,D("400"))
        self.assertEqual(book.locked_cash(),D("14000"))
        self.assertEqual(book.cash,D("100400"))
        self.assertEqual(book.free_cash(),D("86400"))

    def test_conservative_marks_and_quote_staleness(self):
        book=CashSecuredPutLedger(D("100000"))
        q=quote()
        book.sell_put(q,2,stocklens_target=3,mark_underlying=D("80"))
        self.assertEqual(book.mark_equity(D("80"),{q.key:q},"2025-10-21"),D("99980.0"))
        with self.assertRaisesRegex(ValueError,"STALE_SHORT_OPTION_MARK"):
            book.mark_equity(D("80"),{q.key:q},"2025-10-22")

    def test_assignment_payoff_is_not_option_income(self):
        book=CashSecuredPutLedger(D("100000"))
        q=quote()
        book.sell_put(q,2,stocklens_target=2,mark_underlying=D("80"))
        with self.assertRaisesRegex(ValueError,"EXPLICIT_EXPIRY_DATE"):
            book.expire_short_put_at_close(q,D("50"),2,"2025-11-20")
        book.expire_short_put_at_close(q,D("50"),2,"2025-11-21")
        self.assertEqual(book.shares,200)
        self.assertEqual(book.cash,D("86400"))
        self.assertEqual(book.locked_cash(),0)
        self.assertEqual(book.mark_equity(D("50"),{},"2025-11-21"),D("96400"))

    def test_roll_records_close_debit_and_new_premium(self):
        book=CashSecuredPutLedger(D("100000"))
        old=quote()
        book.sell_put(old,2,stocklens_target=2,mark_underlying=D("80"))
        old_close=quote(date="2025-10-30",bid="2.95",ask="3.00")
        new=quote(date="2025-10-30",expiry="2025-12-19",strike="60",bid="4.00",ask="4.20")
        roll=book.roll_down_out(old_close,new,2,stocklens_target=2,mark_underlying=D("80"))
        self.assertEqual(roll["close_at_ask"],D("600"))
        self.assertEqual(roll["new_sale_at_bid"],D("800"))
        self.assertEqual(roll["net_cash_credit"],D("200"))
        self.assertEqual(book.cash,D("100600"))
        self.assertEqual(book.locked_cash(),D("12000"))
        self.assertNotIn(old.key,book.short_puts)
        self.assertIn(new.key,book.short_puts)
        self.assertEqual(len(book.events),3)

    def test_reject_bad_roll_atomically(self):
        book=CashSecuredPutLedger(D("100000"))
        old=quote()
        book.sell_put(old,2,stocklens_target=2,mark_underlying=D("80"))
        a=quote(date="2025-10-30",bid="2.95",ask="3.00")
        bad=quote(date="2025-10-30",expiry="2025-12-19",strike="80",bid="5",ask="5.2")
        before=(book.cash,len(book.events),book.locked_cash())
        with self.assertRaisesRegex(ValueError,"ROLL_DOWN_OUT"):
            book.roll_down_out(a,bad,2,stocklens_target=2,mark_underlying=D("80"))
        self.assertEqual((book.cash,len(book.events),book.locked_cash()),before)

    def test_long_put_hedge_has_cost_and_mark(self):
        book=CashSecuredPutLedger(D("100000"))
        short=quote()
        hedge=quote(expiry="2026-01-16",strike="40",bid="0.9",ask="1.0")
        book.sell_put(short,2,stocklens_target=2,mark_underlying=D("80"))
        cost=book.buy_protection(hedge,1)
        self.assertEqual(cost,D("100.0"))
        self.assertEqual(book.cash,D("100300"))
        marked=book.mark_equity(D("80"),{short.key:short,hedge.key:hedge},"2025-10-21")
        self.assertEqual(marked,D("99970.0"))

    def test_cboe_import_rejects_unverified_contract_adjustment(self):
        columns=[
            "Underlying Symbol","Quote Date","Root","Expiration","Strike",
            "Option Type","Bid 1545","Ask 1545","Bid Size 1545",
            "Ask Size 1545","Open Interest"
        ]
        entry=["TQQQ","2025-10-21","TQQQ","2025-11-21","70",
               "Put","2.00","2.10","100","100","300"]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"sample.csv"
            with path.open("w",newline="") as f:
                writer=csv.writer(f);writer.writerow(columns);writer.writerow(entry)
            with self.assertRaisesRegex(ValueError,"UNVERIFIED_OPTION_DELIVERABLE"):
                import_cboe_csv(str(path),adjustment_verified=False)
            imported=import_cboe_csv(str(path),adjustment_verified=True)
            self.assertEqual(len(imported),1)
            self.assertEqual(imported[0].strike,D("70"))
            self.assertEqual(imported[0].source,"CBOE_EOD_1545")


    def test_rejected_orders_are_side_effect_free(self):
        book=CashSecuredPutLedger(D("100000"))
        with self.assertRaisesRegex(ValueError,"STOCKLENS_CASH_REGIME"):
            book.sell_put(quote(),1,stocklens_target=0,mark_underlying=D("80"))
        self.assertIsNone(book.last_date)
        self.assertEqual(book.events,[])
        self.assertEqual(book.cash,D("100000"))
        with self.assertRaisesRegex(ValueError,"UNRECOGNIZED_STOCKLENS_EXPOSURE"):
            book.sell_put(quote(),1,stocklens_target=5,mark_underlying=D("80"))
        self.assertIsNone(book.last_date)
        with self.assertRaisesRegex(ValueError,"MAX_CASH_SLEEVE"):
            book.sell_put(quote(),3,stocklens_target=2,mark_underlying=D("80"))
        self.assertIsNone(book.last_date)
        self.assertEqual(book.events,[])

    def test_validations_reject_adjusted_root_and_bad_quote(self):
        with self.assertRaisesRegex(ValueError,"WRONG_UNDERLYING_OR_ADJUSTED_ROOT"):
            quote(root="TQQQ1").validate()
        with self.assertRaisesRegex(ValueError,"CROSSED_OR_INVALID_NBBO"):
            quote(bid="2.5",ask="2.1").validate()
        with self.assertRaisesRegex(ValueError,"EXPIRED_OPTION_QUOTE"):
            quote(date="2025-11-21",expiry="2025-11-21").validate()


if __name__=="__main__":
    unittest.main()
