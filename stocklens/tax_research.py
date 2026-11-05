"""SL-50: research-only FIFO/FX capital-gains scenario. NOT a tax return.

Does not change live Paper or broker. Caller supplies dated fills, fees and FX.
FX-indexed treatment is an approximation requiring accountant/broker review.
"""
from dataclasses import dataclass
from decimal import Decimal
from datetime import date

def D(v):
    x = Decimal(str(v))
    if not x.is_finite():
        raise ValueError("NONFINITE_AMOUNT")
    return x

@dataclass
class Lot:
    date: str
    qty: int
    basis_usd: Decimal
    fx: Decimal

class TaxBook:
    def __init__(self, rate="0.25", opening_losses_ils="0"):
        self.rate = D(rate)
        self.losses = D(opening_losses_ils)
        if not 0 <= self.rate <= 1 or self.losses < 0:
            raise ValueError("BAD_TAX_SETTINGS")
        self.lots = {}
        self.realized_usd = D(0)
        self.nominal_ils = D(0)
        self.indexed_ils = D(0)
        self.tax_assessed_ils = D(0)
        self.events = []

    def _check(self, day, symbol, qty, price, fee, fx):
        if date.fromisoformat(day).isoformat() != day or not symbol:
            raise ValueError("INVALID_EVENT")
        if type(qty) is not int or qty <= 0:
            raise ValueError("INVALID_QTY")
        if D(price) <= 0 or D(fee) < 0 or D(fx) <= 0:
            raise ValueError("INVALID_PRICE_FEE_OR_FX")

    def quantity(self, symbol):
        return sum(l.qty for l in self.lots.get(symbol, []))

    def buy(self, day, symbol, qty, fill_usd, fee_usd, fx_ils_usd):
        self._check(day, symbol, qty, fill_usd, fee_usd, fx_ils_usd)
        basis = D(fill_usd) + D(fee_usd) / qty
        self.lots.setdefault(symbol, []).append(Lot(day, qty, basis, D(fx_ils_usd)))
        result = {"date":day,"symbol":symbol,"side":"BUY","qty":qty,
                  "basis_including_fee_usd":str(basis*qty)}
        self.events.append(result)
        return result

    def sell(self, day, symbol, qty, fill_usd, fee_usd, fx_ils_usd):
        self._check(day, symbol, qty, fill_usd, fee_usd, fx_ils_usd)
        if qty > self.quantity(symbol) or D(fee_usd) >= D(fill_usd)*qty:
            raise ValueError("INSUFFICIENT_LOTS_OR_FEE")
        fx = D(fx_ils_usd)
        net_unit = D(fill_usd) - D(fee_usd)/qty
        remaining = qty
        indexed = D(0)
        nominal = D(0)
        gain_usd = D(0)
        consumed = []
        while remaining:
            lot = self.lots[symbol][0]
            n = min(remaining, lot.qty)
            usd_change = (net_unit - lot.basis_usd)*n
            gain_usd += usd_change
            indexed += usd_change*fx
            nominal += (net_unit*fx - lot.basis_usd*lot.fx)*n
            consumed.append({"date":lot.date,"qty":n,"basis_usd":str(lot.basis_usd)})
            lot.qty -= n
            remaining -= n
            if lot.qty == 0:
                self.lots[symbol].pop(0)
        # Exclude FX-only losses; do not tax indexed gains that are nominal losses.
        eligible_gain = min(max(D(0),nominal), max(D(0),indexed))
        eligible_loss = min(max(D(0),-nominal), max(D(0),-indexed))
        offset = min(eligible_gain, self.losses)
        self.losses += eligible_loss-offset
        tax = (eligible_gain-offset)*self.rate
        self.tax_assessed_ils += tax
        self.realized_usd += gain_usd
        self.nominal_ils += nominal
        self.indexed_ils += indexed
        result = {"date":day,"symbol":symbol,"side":"SELL","qty":qty,
                  "net_proceeds_usd":str(net_unit*qty),
                  "realized_usd":str(gain_usd),"nominal_ils":str(nominal),
                  "fx_indexed_ils":str(indexed),"eligible_gain_ils":str(eligible_gain),
                  "eligible_loss_ils":str(eligible_loss),"loss_offset_ils":str(offset),
                  "estimated_incremental_tax_ils":str(tax),
                  "fifo_consumed":consumed}
        self.events.append(result)
        return result

    def summary(self):
        return {"mode":"RESEARCH_PRETAX_PAPER_UNCHANGED",
                "tax_assessed_ils":str(self.tax_assessed_ils),
                "unused_loss_pool_ils":str(self.losses),
                "realized_usd":str(self.realized_usd),
                "nominal_realized_ils":str(self.nominal_ils),
                "fx_indexed_realized_ils":str(self.indexed_ils),
                "holdings":{s:self.quantity(s) for s in self.lots},
                "tax_was_withheld":False}
