# SL9-031 — ST observed ETF and risk-overlay combinations (preregistered 2026-10-28)

Historical **falsification**, not clean OOS. The 2010–2026 sample is repeatedly inspected; no model promotion.

Fixed 7 ETF sleeve modes: frozen (100% TQQQ); q3_upro25, q3_soxl25, q3_tecl25, q3_fas25 (TQQQ 75%, alternate ETF 25%); q3_soxl12_tecl12 (TQQQ 75%, SOXL 12.5%, TECL 12.5%); q3_upro12_soxl12 (TQQQ 75%, UPRO 12.5%, SOXL 12.5%).

Weights apply to **the TQQQ component of the chosen QQQ/TQQQ leverage**, in all invested states (not just frozen 3x). The QQQ sleeve remains unchanged. Frozen 0x is entirely cash. Nasdaq signal may not be appropriate for the other sectors.

Fixed eight risk overlays: frozen, cap2, cap2_5, ewma5_shock, vol60_instant, vol60_ramp5, staged_up3, vol60_ramp5_ewma5. Existing EWMA5 shock cap and Vol60 realized volatility logic are reused with completed *prior* QQQ closes, and the Vol60 5-open upward ramp increases allowed leverage by no more than 0.4 per session. Staged up over 3 sessions never delays exits to frozen zero. Combined cap is min of both existing caps. No same-open close leakage.

**Fixed 56 factorial arms × four stress cases = 224 backtests.** Additional decision/feature delay: 0 or 1 sessions. Per side slippage: 10 or 20 bps, plus 2 bps fees. Primary = lag1/10bps. The frozen reference has identical costs/lag. Account starts with $100,000, no deposits, tax, FX or cash interest. All whole-share executions are modeled at real **Yahoo auto-adjusted daily OPEN**, not market-maker quotes or broker fills.

Source: fixed original observed UPRO, SOXL, TECL and FAS bars from Green GitHub run 40730235493 artifact stocklens-st-real-3x-observed-comparison. Exact original bars SHA, frozen base snapshot, and period must match. No data imputation, provider switching, ETF synthetic 3x backfill or return multipliers. The full history only runs from common inception (2010), not from 1986.

Descriptive risk breakdown: full-period CAGR, MaxDD, annual vol, whole-share trades/turnover, and continuous-account eras 2010–17, 2018–22, 2023–26; crisis snapshots 2020 COVID and 2022. Do NOT optimize based on eras.

**Continuation-only gate, fixed in advance:** +0.5 percentage points CAGR without >1 percentage point MaxDD deterioration versus matched frozen in all four cost/lag cases. Even passing cannot promote a model. 55 simultaneous comparisons mean data-snooping/multiple-testing bias. Preserve negative results.

No broker orders, no AWS ST write, no PROD write. CI artifact/dashboard is historical, not independent second-provider validation, not a pristine holdout, not forward Paper. Separate AWS upload receipts, real execution, alerts, second vendor and future out-of-sample testing are mandatory.
