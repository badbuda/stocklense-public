# SL9-020b — QQQ×3 forward proxy against actual observed TQQQ adjusted closes

**Retrospective source reconciliation, not actual brokerage execution or prospective alpha.**

Evidence source files: `docs/portal-history.json` Git blob `c9ce87cdd40692f77fab883d86ad6692dabeb050`; `research/prospective/SL9-007-UPSHIFT-CONFIRMATION.csv` Git blob `4b294be70603b57e439a836f6663a25052535d1b`. Both rely on Yahoo-derived adjusted data; not an independent second provider.

Compare SL9-007 model baseline_return (QQQ daily return multiplied by frozen 3x exposure) to TQQQ genuine observed ETF adjusted close-to-close return. The latter is **not synthetic**; neither is an intraday or actual broker fill.

| Session | Model QQQ×3 | Actual TQQQ adjusted close return | Model − real, bp |
|---|---:|---:|---:|
| 2026-09-28 | -3.212% | -3.216% | 0.45 |
| 2026-09-29 | 0.570% | 0.545% | 2.51 |
| 2026-09-30 | 0.748% | 0.736% | 1.22 |
| 2026-10-01 | 0.917% | 0.897% | 1.94 |
| 2026-10-02 | 3.052% | 2.896% | 15.65 |
| 2026-10-05 | 2.649% | 2.605% | 4.49 |
| 2026-10-06 | 1.373% | 1.359% | 1.32 |
| 2026-10-07 | -0.762% | -0.748% | -1.44 |
| 2026-10-08 | -4.019% | -4.054% | 3.55 |
| 2026-10-09 | 1.481% | 1.309% | 17.20 |

**10 aligned sessions:** mean absolute daily difference **4.98 bp**, maximum **17.20 bp**.
Compounded ten-session modeled return **2.5831%** vs genuine TQQQ observed adjusted-close return **2.1106%**. Model minus ETF ending wealth **47.26 bp** of starting capital.

These small-sample differences are ETF tracking/measurement proxy deviations, NOT observed brokerage slippage; this CSV still lacks independently certified original forward collection timestamps. Frozen 8.0 is not changed: its separate 2010–2026 observed-QQQ/TQQQ daily-open research remains distinct. No trades or promotion.
