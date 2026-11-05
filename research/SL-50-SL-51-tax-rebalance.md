# SL-50 / SL-51 — Tax-aware Paper research and rebalance costs

**Status: research prototype; NO change to frozen 8.0, running ST Paper, PROD, broker, or published live NAV.** This is not a tax determination. Tax rates, FX-indexation interpretation, lot identification, annual offsets and withholding are assumptions requiring independent 2026 Israeli-tax/broker review.

## Existing baseline verified in code

- `stocklens/core.py`: 98.5% invested fraction. Level 3: 98.5% TQQQ; level 2: 49.25% each QQQ/TQQQ; level 1.25: 86.1875% QQQ and 12.3125% TQQQ; defense: 100% cash.
- `stocklens/paper.py` / `paper_rebalance_math.py`: sells excess WHOLE shares at next-open 09:31 NY; buys needed shares at 09:32 NY. 2 bps brokerage fee and 10 bps modeled one-way slippage. `NO_CHANGE` suppresses trading only if the largest target-weight deviation is at most 50 bps; changed risk level triggers a rebalance. It is NOT an unconditional whole-account liquidation.
- Frozen Paper currently charges **no capital gains tax** and does not contain broker tax lots or FX history. The last authenticated ST Paper receipt for 2026-11-04 contains 1,549 TQQQ, 0 QQQ, $1,435.15 cash, $97,796.89 gross NAV; history has one 2026-10-30 purchase and zero sales through Nov 4. **There is no realized capital-gain sale in these four sessions, so a sale-triggered tax scenario does not explain current -2.20% performance.**
- This new research branch must never be deployed or auto-promoted to production.

## Implemented research modules

- `stocklens/tax_research.py`: separate FIFO lot ledger with purchase fees included in cost, sale fees netted from proceeds, partial sales, ILS nominal and FX-indexed realization side by side, illustrative eligible gains/losses, forward loss offset, configured nominal 25% research rate. Tax is **assessed for scenario comparisons, not subtracted from the operating Paper account**. This is a simplified per-trade model, not an annual Israeli tax return.
- `research/paper_tax_receipts.py`: replays a receipt's **full trade history**; requires verified receipt SHA256 and actual dated ILS/USD rates from user-supplied JSON. Checks modeled-only book status, trade counts, and final shares. Keeps gross NAV separate from indicative after-tax value. No AWS writes.
- `research/rebalance_tax_study.py`: takes immutable point-in-time market/FX and lagged-signal inputs, performs fixed-share target sell-before-buy planning, comparing original 50-bp NO_CHANGE band with 100-/200-bp research bands, both gross and an explicitly **hypothetical immediate tax-withholding scenario**. Exits for defense remain mandatory. Reports turnover, fees, slippage, tax-assessed, NAV, DD, trades and daily ledgers. It separately reports an **illustrative month-end tax-netting/within-year-credit projection** based on realized trade events. This projection does NOT debit actual broker cash or claim to reproduce broker timing.
- `tests/test_tax_research.py`, `tests/test_rebalance_tax_study.py`, `tests/test_paper_tax_receipts.py`: control/edge-case tests.

### Reproducible local commands

```bash
python -m pytest -q tests/test_tax_research.py tests/test_rebalance_tax_study.py tests/test_paper_tax_receipts.py
python research/rebalance_tax_study.py --input research_observed_sessions.json --output tax_rebalance_comparison.json
python research/paper_tax_receipts.py --receipt st_paper_2026-11-04.json --sha256 797bccafa9aba7b3799c312bbd1ed2f67e0101c127f2bcbdec6318d91f2f22d2 --fx verified_ils_per_usd.json --out st_tax_research.json
```

Example observed session input row (real dates/prices required; this is **schema**, not market data):

```json
{"date":"YYYY-MM-DD","leverage":2.0,"action":"REBALANCE_NEXT_SESSION",
 "qqq_0931":100,"qqq_0932":100,"qqq_close":100,
 "tqqq_0931":100,"tqqq_0932":100,"tqqq_close":100,
 "fx_ils_per_usd":3.5}
```

Rates must be sourced from actual historical evidence; synthetic 100/3.5 above MUST NOT be used as a historical run. The comparison is not a valid historical backtest until an independently verified point-in-time session series, full prior state, spread/fee assumptions, corporate actions, and exchange-rate provenance are supplied. Backtest optimization requires walk-forward, OOS crisis holdouts, source parity, LOCO and zero lookahead — do not choose a winner from toy fixture results.

## Tax interpretation boundaries / outstanding acceptance

- Israeli Tax Authority Form 1322 for 2025 states 25% standard real capital gains for qualifying individual securities, subject to applicable classifications. [Official form 1322](https://www.gov.il/he/service/reporting-and-payment-2025-annual-tax-report-for-individuals).
- Circular 10/2025 explains tax losses, including FX-only losses on foreign-currency securities. [Official circular](https://www.gov.il/BlobFolder/policy/professional-directives-271125-1/he/IncomeTax_professional-directives-271125-1.pdf).
- Excellence's own [trading FAQ](https://lp.xnes.co.il/bursa_xnes_trade/live_course/) describes monthly aggregation of realized profits and losses, end-of-month tax display, and possible credits within the same calendar year. Immediate per-sale withholding is therefore a stress-test assumption, **not** verified Excellence cashflow.
- **Broker fee gap:** the frozen Paper's 2 bps per trade is not equivalent to the per-share/minimum US-trading commission examples published by Excellence; the actual client's negotiated tariff and charges must be verified before claiming after-fee returns.
- Surtax can depend on **total annual individual and capital income**, not just individual trade profit. Research 25% ignores thresholds and additional taxes. [Israel Tax Authority supplementary-tax circular](https://www.gov.il/BlobFolder/policy/inst-05-2025/he/IncomeTax_inst-05-2025.pdf).
- FIFO is a scenario; the lawful/broker-determined lot allocation must be confirmed. The model uses sale-date FX indexing with a conservative nominal/indexed cap; the exact loss/gain offsets require accountant review, especially cross-year offsets, excess tax previously paid, dividend withholding, splits, currency changes and multi-account offsetting.
- **Actual Excellence Trade withholding is UNKNOWN** without broker tax/cost-basis statements. `immediate_tax_withholding=True` is an economic research scenario, not evidence of a cash debit. The Paper history does not itself provide purchase/sale-date ILS/USD evidence. Missing dates fail closed. There is no broker API or receipt access in this branch.
- No claims of after-tax CAGR for the real 2009–2026 or post-2010 ETF portfolio until a verified market/FX dataset is supplied and OOS tests are green. No publication as real NAV and no PROD promotion.

## SL-50 acceptance next review

Verify 2026 applicable rules / FIFO / FX / annual loss carry and withholding timing with accountant plus redacted Excellence 867 and lot statements. Add true cash-debit timestamps, year-end reconciliation, split/dividend cases, consistent broker lots and independent calculation parity; then user-approved integration into a SEPARATE tax view (never overwrite gross Paper NAV).

## SL-51 acceptance next review

Run on point-in-time observed QQQ/TQQQ minute bars and tax FX dataset; document eligible tax losses, realized turnover and after-tax wealth including increased risk from deferring rebalancing. Run unchanged frozen 8.0 benchmark, no-change bands, crises/OOS, walk-forward and variance-matched comparison. Do not weaken urgent cash exits or run experiments in PROD.
