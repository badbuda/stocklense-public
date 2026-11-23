"""Research-only illustrative Israeli capital-gains lot accounting, NOT tax advice.

FIFO, NIS-denominated nominal basis, configurable flat rate, immediate settlement.
No inflation indexation, foreign-currency tax basis exceptions, withholding, carryovers,
dividends, corporate actions or legal determination. Do not promote to trading.
"""
from dataclasses import dataclass
from decimal import Decimal

def D(value):
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError("NONFINITE_AMOUNT")
    return d

@dataclass
class Lot:
    quantity: Decimal
    basis_nis: Decimal

class TaxLedger:
    def __init__(self, rate="0.25"):
        self.rate = D(rate)
        if not 0 <= self.rate <= 1:
            raise ValueError("INVALID_RATE")
        self.lots = []
        self.realized_nis = Decimal(0)
        self.tax_paid_nis = Decimal(0)
        self.loss_pool_nis = Decimal(0)

    def buy(self, quantity, price_usd, fx_nis_per_usd, fee_nis="0"):
        q, p, fx, fee = map(D, (quantity, price_usd, fx_nis_per_usd, fee_nis))
        if q <= 0 or p <= 0 or fx <= 0 or fee < 0:
            raise ValueError("INVALID_BUY")
        self.lots.append(Lot(q, q * p * fx + fee))

    def sell(self, quantity, price_usd, fx_nis_per_usd, fee_nis="0"):
        q, p, fx, fee = map(D, (quantity, price_usd, fx_nis_per_usd, fee_nis))
        if q <= 0 or p <= 0 or fx <= 0 or fee < 0:
            raise ValueError("INVALID_SELL")
        if fee > q * p * fx:
            raise ValueError("FEE_EXCEEDS_GROSS_PROCEEDS")
        if q > sum((lot.quantity for lot in self.lots), Decimal(0)):
            raise ValueError("INSUFFICIENT_SHARES")
        # Compute on detached copies: Decimal arithmetic failures must never
        # leave a partially consumed FIFO ledger.
        pending = [Lot(lot.quantity, lot.basis_nis) for lot in self.lots]
        remaining, basis = q, Decimal(0)
        while remaining:
            lot = pending[0]
            take = min(remaining, lot.quantity)
            consumed = lot.basis_nis * take / lot.quantity
            basis += consumed
            lot.basis_nis -= consumed
            lot.quantity -= take
            remaining -= take
            if lot.quantity == 0:
                pending.pop(0)
        gain = q * p * fx - fee - basis
        loss_pool = self.loss_pool_nis
        if gain < 0:
            loss_pool += -gain
            tax = Decimal(0)
        else:
            offset = min(gain, loss_pool)
            loss_pool -= offset
            tax = (gain - offset) * self.rate
        self.lots = pending
        self.realized_nis += gain
        self.loss_pool_nis = loss_pool
        self.tax_paid_nis += tax
        return {"realized_gain_nis": gain, "tax_nis": tax,
                "net_proceeds_nis": q * p * fx - fee - tax,
                "remaining_loss_pool_nis": self.loss_pool_nis}
