# SL724 locked original LEAN order quotes — native execution audit (2026-10-10)

## Input identity and scope

- The original **private** QuantConnect `Determined Red Orange Duck.json` was found in the owner's file Library, read locally and verified against the pinned SHA-256 `65cb291e6552dc0f86b32106bc3fe3f7a7ed8a127b3d0d6f84a60a8f5800b6f7`. The complete raw JSON was **not** uploaded to public GitHub.
- The original chart contains **3,774 native SL724 daily leverage/NAV/drawdown rows**, spanning 2009–2024, and **345 filled simulated orders** with LEAN `orderSubmissionData` bid/ask/last + LEAN simulated fill. These quotes are **inside LEAN**, not independent venue NBBO or actual brokerage executions.
- Native simulated trades by instrument: **251 TQQQ, 87 QQQ, 7 QLD**.
- New reusable local forensic verifier: `qc_native_original_execution_forensics.py`, compares private JSON bytes to locked SHA, validates chart/order counts, timestamps, symbol, signed integer quantity, positive fill/bid/ask/last and non-crossed LEAN simulated spread. Native raw order/quote data is deliberately not committed. Synthetic CI fixtures must never imply original source authenticity.

## LEAN simulated fill vs the quote on order submission (not realized slippage)

Directional quote deviation: `10000 * (fill / (ask if buy else bid) - 1) * (+1 if buy else -1)`. Positive = simulated fill worse than the quoted side, negative = simulated fill better. **Do not equate fill vs last or quote with broker market slippage.**

| Instrument | Filled orders | Median directional fill-to-side quote | 95th percentile approx | Number of absolute 50bp outliers |
|---|---:|---:|---:|---:|
| QLD | 7 | +0.0027 bps | +0.95 bps | 0 |
| QQQ | 87 | +0.1648 bps | +4.26 bps | 0 |
| TQQQ | 251 | +0.0055 bps | +10.00 bps | **3** |

**All-event 50bps threshold:** five TQQQ order records trip at least one of three diagnostics: fill-to-side quote, fill-to-last, or internal simulated quoted spread. Three exhibit absolute side-quote differences over 50bps; one has an exceptional last-vs-fill deviation >600bps and four exhibit internal quoted spread >50bps. Events can overlap; **do not sum the three categories to count unique orders**.

Three directional fill-to-side-quote outliers, kept as aggregates (not raw LEAN order records):
- 2011-12-02 TQQQ buy **+162.93bps** unfavorable vs its LEAN ask; internal spread ~109bps.
- 2013-01-03 TQQQ buy **−55.32bps** favorable vs its LEAN ask; do not misleadingly call this a 55bps execution loss.
- 2015-10-01 TQQQ buy **+54.97bps** unfavorable vs its LEAN ask; internal spread ~111bps.

Two other spread/last anomalies arose on 2015-08-24. Native simulated spreads there reached about **211bps**, and a fill-versus-last comparison reached about **619bps**. This may reflect unstable historical quote/adjustment semantics or simulated execution; without timestamped independent tapes we cannot adjudicate it.

**Implication:** a universal assumed 10bps per-side slippage is a stress convention, not a measurement of the original 345 orders. Old LEAN simulated spreads and unusual fills deserve scrutiny, especially near crisis transitions, before any live order sizing.

## What remains blocked despite this original-source discovery

1. **Same-input LEAN features:** original JSON does **not** contain native `close,sma50,sma200,vol20,mom12` for all 3,774 sessions; only original daily leverage/NAV/drawdown. See `governance/LEAN_FREE_FEATURE_EXPORT.md` for the observer-only QuantConnect diagnostic run, preserving the original code/data.
2. **Exact LEAN portfolio and external contributions:** a native daily portfolio/NAV/cash/positions and order execution export with identical execution semantics is still required for independent same-start comparison. The original chart's NAV multiple is not enough.
3. **Independent quote provenance:** original LEAN `orderSubmissionData` is not a broker-certified NBBO snapshot. Obtain timestamped vendor/broker bid/ask, order responses and fill reports; verify timestamps, trade direction, adjustments, corporate actions, order identifiers and full raw hash-chain.
4. **Forward evidence:** continue unretuned prospective 8.0 paired Paper for 63/252 completed sessions, with explicit missing-day accounting. No synthetic backfill.

## How to reproduce securely

Run locally only, with original results outside the public repo:

```bash
python qc_native_original_execution_forensics.py \
  --original "/private/Determined Red Orange Duck.json" \
  --out research/local/native_sl724_order_quote_forensics.json
```

The CLI defaults to private ignored `research/local` output and refuses nonmatching original SHA unless invoked through a synthetic fixture call in tests; no real broker connection is performed. For full same-input future-proofing continue with `qc_chart_feature_acquisition.py` only on a privately instrumented original LEAN project copy. Avoid changing frozen StockLens 8.0.

**Decision:** native simulated execution quote anomalies are now *documented and reproducible against the verified original file*, but **real fills, native input feature identity and alpha remain NOT PROVEN**. No capital or automatic model promotion.
