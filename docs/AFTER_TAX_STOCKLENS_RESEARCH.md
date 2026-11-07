# StockLens after-tax comparison — research-only (2026-11-07)

This change does **not** alter frozen StockLens 8.0 signals, the ST/PROD paper
account, AWS schedules, the public live NAV, or any brokerage account. All
values here are **counterfactual** model outputs, not an Israeli tax assessment
or actual Excellence Trade deductions.

## What the model now exposes

`research/rebalance_tax_study.py --input verified_sessions.json --output comparison.json`
runs the existing observed-point-in-time replay for frozen 8.0 target shares
alongside a **hypothetical immediate-per-sale tax debit**.

Each run now records:
- Modeled 2 bps fee and 10 bps one-way slippage; not verified client tariff.
- FIFO research lots; purchase fee in cost basis; sale fee in proceeds.
- Simplified 25% estimated Israeli capital-gain tax, subject to nominal and
  FX-indexed ILS limits and simplified forward loss offset.
- Daily cumulative estimated assessed tax and cash actually debited **only in
  the hypothetical immediate-debit scenario**.
- `terminal_liquidation_research`: simulated sale of **remaining whole
  shares at the last dated close**, including estimated exit slippage, fees
  and **incremental** tax on those shares. Existing charged hypothetical tax
  is never charged a second time. In the baseline research scenario previous
  assessed tax has not been taken out of NAV; the terminal illustration
  subtracts that unpaid provisional tax as well.

The **tax-wrapper illustration** separately shows the after-trade/exit-cost
value of a hypothetical *tax-exempt* savings wrapper, but it is **not**
confirmation that a specific IRA account is eligible, that TQQQ is tradable
there, or that a withdrawal is tax exempt. It excludes IRA management fees,
the underlying fund's non-return-visible costs, withholding on foreign-source
income, and any product-specific withdrawal or deposit restrictions.

## Key constraints / fail-closed criteria

- No 2010–2026 **after-tax** CAGR or live return claim without dated,
  verified full point-in-time QQQ/TQQQ execution, FX and opening positions.
- No inferred, constant or fabricated USD/ILS rates for backtest history.
- Immediate debit deliberately stresses reduced buying power; it does **not**
  reproduce Excellence's monthly withholding/netting and later credits.
- FX-only losses, cross-year offsets, realization lot selection, possible
  surtax, dividend taxation, annual return and actual withholding are NOT
  independently verified by this simplified `TaxBook`. Terminal valuation
  translates prior unpaid ILS tax at the last day's FX for illustration;
  this can differ from the broker's actual cash timing.
- End-of-test liquidation is for comparing economic wealth and **is not
  a request to close any positions**.
- A taxable broker, an IRA/pension wrapper, a qualifying tax-exempt education
  fund and a private hedge fund have **different tax laws**. Do not model them
  all as a blanket 25%-at-withdrawal account.
- Any real deployment must first obtain the client's negotiated commission
  table, verified tax/FX ledger, accountant/broker interpretation and
  independent acceptance tests. A green CI test only means test correctness,
  not historical/real trading profitability.

## Minimal checks

```bash
python -m pytest -q tests/test_rebalance_tax_study.py tests/test_tax_research.py tests/test_tax_terminal_wealth.py
```

Related: `research/SL-50-SL-51-tax-rebalance.md` and
`docs/TQQQ_GO_NO_GO_PROTOCOL.md`.

Relevant legal/operator references:
- https://www.gov.il/he/service/reporting-and-payment-2025-annual-tax-report-for-individuals
- https://www.meitav.co.il/trade/ira_trade/
