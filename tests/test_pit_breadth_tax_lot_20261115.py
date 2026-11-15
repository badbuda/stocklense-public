"""Synthetic contract checks only; no claim of Israeli tax-law compliance."""
import unittest
from decimal import Decimal
from research.pit_breadth_tax_lot_20261115 import TaxLedger

class TestTaxLots(unittest.TestCase):
    def test_fifo_partial_and_tax(self):
        x=TaxLedger()
        x.buy(10,10,3)
        x.buy(10,20,3)
        r=x.sell(15,30,3)
        self.assertEqual(r["realized_gain_nis"],Decimal(750))
        self.assertEqual(r["tax_nis"],Decimal("187.50"))
        self.assertEqual(x.lots[0].basis_nis,Decimal(300))
    def test_fx_changes_nis_gain(self):
        x=TaxLedger()
        x.buy(1,100,3)
        self.assertEqual(x.sell(1,100,4)["tax_nis"],Decimal(25))
    def test_losses_offset_subsequent_gain_only(self):
        x=TaxLedger()
        x.buy(1,100,3)
        self.assertEqual(x.sell(1,50,3)["tax_nis"],0)
        x.buy(1,50,3)
        self.assertEqual(x.sell(1,100,3)["tax_nis"],0)
    def test_no_future_loss_refund(self):
        x=TaxLedger()
        x.buy(1,50,3)
        self.assertEqual(x.sell(1,100,3)["tax_nis"],Decimal("37.50"))
        x.buy(1,100,3)
        self.assertEqual(x.sell(1,50,3)["tax_nis"],0)
        self.assertEqual(x.tax_paid_nis,Decimal("37.50"))
    def test_fees_affect_basis_and_proceeds(self):
        x=TaxLedger()
        x.buy(1,100,3,10)
        self.assertEqual(x.sell(1,200,3,10)["realized_gain_nis"],Decimal(280))
    def test_reject_oversell_without_mutation(self):
        x=TaxLedger()
        x.buy(1,100,3)
        with self.assertRaises(ValueError): x.sell(2,200,3)
        self.assertEqual(x.lots[0].quantity,1)
    def test_reject_nonfinite(self):
        x=TaxLedger()
        with self.assertRaises(ValueError): x.buy(1,"NaN",3)
    def test_reject_invalid_rate(self):
        with self.assertRaises(ValueError): TaxLedger("1.1")
if __name__ == "__main__":
    unittest.main()
