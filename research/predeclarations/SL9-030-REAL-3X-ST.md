# SL9-030 — isolated ST research: observed 3x ETF alternatives (preregistered 2026-10-28)

**Frozen control:** original StockLens 8.0 QQQ/TQQQ decision levels, not retuned.
The existing QLD substitution was tested and rejected under SL9-015. Do not relabel
that already-reviewed result as a new discovery.

**New ETF shortlist (actual adjusted daily OHLC only):** UPRO (3x S&P 500),
SOXL (3x semiconductors), TECL (3x technology), FAS (3x financials).
All products target **daily** leverage. Their rolling holding-period returns
are not 3 times cumulative index returns. No inverse or single-stock products.

**Exactly 9 locked arms on an identical shared data window:**
- Frozen 8.0 100%.
- At **frozen level 3 ONLY**, replace its TQQQ allocation by UPRO/SOXL/TECL/FAS
  (four arms), or blend TQQQ 75% + candidate 25% (four arms).
- At frozen levels 0, 1.25, 2: preserve original QQQ/TQQQ/cash *exactly*.
- Alternate 3x ETF uses the unchanged QQQ signal, **not** its own fitted SMA or
  thresholds. This may cause regime mismatch; do not retro-fit until clean OOS.

**Source/ledger:** Published real QQQ/TQQQ adjusted open/close, independently
downloaded real Yahoo adjusted UPRO/SOXL/TECL/FAS Open/Close, no index-return
multiplication, and no quote interpolation. All instruments must cover the
same exchange sessions, beginning only when the newest fund started. Fail
closed on a missing day or provider error. Whole shares, $100,000, 98.5%
invested fraction, trades on next daily adjusted OPEN (proxy, not 09:31 NBBO);
2 bps fee/side, 10 or 20 bps slippage/side; extra decision lag 0 or 1.
**Primary** = extra lag 1, 10 bps. Compare frozen with same lag/cost.
No contributions, taxes, FX, true broker spread or cash yield.

**Screen selected before results:** gain >=0.5 percentage points CAGR without
worsening MaxDD by >1 pp in *each* of the 4 delay/cost scenarios. This is
only a reason for **additional** research and not a model promotion rule.
Check raw equity end, MaxDD, CAGR, number of trades and common-source hash.

**Claims prohibited:** independent vendor parity, untouched holdout,
genuine broker fills, prospective AWS Paper, live strategy improvement,
autonomous promotion. The reused historical 2010–2026 data cannot establish
an investable alpha advantage. No PROD or broker writes are authorized.

**Operational scope:** CI research artifacts and optional read-only dashboard
snapshot are not proof of AWS ST deployment. AWS publication must be
checked independently inside \`stocklens-st\` only; never deploy to PROD.
