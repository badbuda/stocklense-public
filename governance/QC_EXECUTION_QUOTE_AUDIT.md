# QuantConnect fill/quote forensic gate (offline, no synthetic fill proof)

Source: private *Adaptable Green Buffalo* and *Emotional Green Chimpanzee* LEAN backtest JSON files. They are **not committed** to this public repository. The newer run adds QC native chart quotes; it is a 7.33 observer of frozen 7.24 decision rules, not recovered original 7.24 code.

Run locally (only Python standard library is required):

```bash
python qc_execution_quote_audit.py "/private/Emotional Green Chimpanzee.json" \
  --prior "/private/Adaptable Green Buffalo.json" \
  --out "research/local/qc_execution_quote_audit.json"
```

This produces a **diagnostic**, not independent broker fills. It requires a real order `orderSubmissionData` record for bid/ask/last, takes **Ask for buys and Bid for sells**, reports signed fill-vs-side-quote and separate signed fill-vs-last, and never equates either to broker slippage. Chart quotes are joined only on exact UTC timestamp, not just date. Split-adjusted historical prices must never be mistaken for live actual tape spreads. Nonfinite, nonpositive or crossed quotes fail closed. Missing/nonfilled orders are disclosed as incomplete coverage.

Separate alert categories:
- `abs(fill_vs_last_directional_bps_NOT_SLIPPAGE) > 50`: includes quote/last asynchrony, not proof of slippage.
- `abs(fill_vs_side_quote_directional_bps) > 50`: unusual fill-vs-submission-side quote.
- `submission_spread_bps > 50`: unusually wide recorded bid/ask.

On the October 2026 private QC sample, all **345** orders had bid/ask/last; 87 QQQ, 7 QLD and 251 TQQQ. Five records triggered at least one alert. TQQQ's median recorded spread was about 3.57 bps; **maximum about 210.62 bps**. A ~619.43 bps fill-vs-last reading in August 2015 does **not** represent measured market slippage. Both QC runs' exact order records, native observer feature charts, statistics and runtime stats matched. These values are immutable observations of the supplied runs, not guarantees on unseen future fills.

Never promote this audit to `LEAN_ORDER_PARITY_PROVEN`, `BROKER_EXECUTION_PROVEN`, `LIVE_READY` or alpha evidence. Actual market quotes/trades, historical venue conditions and out-of-sample paper execution are still needed. Do not weaken outlier thresholds or silently drop extreme dates to make a report green. Fee model and execution assumptions should be stress-tested separately, without modifying the 7.24 frozen strategy.
