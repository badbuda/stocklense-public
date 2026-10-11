# StockLens SL9-014 — EFFR cash sensitivity and fixed-sleeve crisis study (2026-10-11)

**Decision: StockLens 8.0 unchanged; no new promoted challenger, no live broker trading.**

## Audited CI and locked data

- PR #59 (merged): https://github.com/badbuda/stocklense-public/pull/59
- Final green Fast Guard: https://github.com/badbuda/stocklense-public/actions/runs/38109533020
- Full original result JSON / human reports: https://github.com/badbuda/stocklense-public/actions/runs/38109533020/artifacts/11690892986 (30-day retention).
- **509 pytest tests passed**; first CI attempt failed on missing market-date-array input to an era reporter, diagnosed and fixed with targeted regression before final green.
- Observed Yahoo-adjusted genuine QQQ/TQQQ daily OPEN/CLOSE (NOT synthetic TQQQ), 4,191 stock market sessions Feb 11, 2010–Oct 9, 2026; market snapshot digest `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
- Same date-aligned genuine observed GLD and TLT Yahoo-adjusted bars, digest `2f680455c1ba81eb2e859eb9520efb2c1139d2e2861ba715c697712004ee2210`. Independent provider cross-audit NOT done.
- NY Fed EFFR actual *effective-date* historical observations: **4,186** (Feb 11, 2010–Oct 8, 2026), from prior successful source acquisition CI #38108795287. **The actual dates when each observation first became available to the market are NOT independently attested.**

## Conditional interest sensitivity (zero contributions, unchanged frozen trade decisions)

The study applies a deliberately conservative **hypothetical 2-completed-NYSE-session information delay** to the EFFR effective dates, never asserting that this models actual archival first-seen. First two sample dates have zero-interest warmup because earlier source history was not fetched. Only the modeled cash balance earns interest; ETF share trades retain the previous whole-share fee/slippage engine and zero-rate NAV reproduces the frozen baseline.

| Conditional modeled cash credit | CAGR | Incremental CAGR vs zero yield |
|---|---:|---:|
| **Zero-interest StockLens 8.0** | **40.0263%** | 0 pp |
| EFFR less 200bps, floor 0 | 40.1157% | +0.08934 pp |
| EFFR less 100bps, floor 0 | 40.1848% | +0.15844 pp |
| EFFR full, no haircut | 40.2709% | +0.24463 pp |

**Not broker interest evidence.** EFFR is an overnight wholesale reference, not a signed retail/brokerage cash sweep contract. Effective-date vintage is not proven publication first-seen; no income taxation, FX, broker financing rate, interest entitlement or real fills was verified. This is descriptive conditional accounting, not investable alpha, a new challenger, or a historically proven rate-credit track record.

## Preregistered crisis-window outcome attribution of previous fixed sleeves

The following are **close-to-close returns across the fixed historical windows**, not independent maximum drawdowns within each portfolio's own peak-to-trough path. Fixed mixes remain 85% frozen / 7.5% GLD / 7.5% TLT and 70% frozen / 15% GLD / 15% TLT. Original frozen 8.0 preserved; no parameter retuning.

| Crisis window | Frozen 8.0 | 85/7.5/7.5 | 70/15/15 |
|---|---:|---:|---:|
| 2015-07-20 – 2016-06-27 | -49.0756% | -41.1846% | -32.7797% |
| 2020-02-19 – 2020-03-16 | -48.6077% | -42.7463% | -36.4110% |
| 2021-11-19 – 2022-05-06 | -47.6898% | -42.4662% | -37.3054% |
| 2018-10-01 – 2019-01-02 | -38.3365% | -33.5681% | -28.4445% |

Worst single modeled trading-day loss:

| Portfolio | Worst-day close-to-close |
|---|---:|
| Frozen | -15.2580% |
| 85/7.5/7.5 | -14.0727% |
| 70/15/15 | -12.6719% |

All three worst single trading days occurred on 2020-09-03.

Full-history portfolio-specific maximum drawdowns:

| Portfolio | MaxDD | Modelled round/side order count |
|---|---:|---:|
| Frozen | -49.0756%, peak Jul 20 2015 / trough Jun 27 2016 | 147 |
| 85/7.5/7.5 | -43.7717%, peak Nov 19 2021 / trough Oct 24 2022 | 339 |
| 70/15/15 | -40.1518%, peak Nov 19 2021 / trough Oct 24 2022 | 342 |

The fixed sleeves materially reduced several historical crisis losses but failed the prespecified return-risk continuation hurdle from SL9-013. Whole-sample CAGR fell from **40.0263%** to **36.5802%** and **32.5180%** respectively; 0/4 lag/cost robustness continuation cases passed for each. Their increased trade counts create additional real-broker execution/FX exposure not captured by historical daily adjusted open pricing.

## Remaining blockers; no justified new alpha assertion
1. Independently verify historical price adjustments, quote timing and actual 09:31/09:32 broker fills, especially the severe gap days.
2. Obtain contractual **Excellence Trade** cash rates, cash sweep eligibility, minimum fee, FX spreads and margin/funding costs before reporting realizable EFFR cash alpha.
3. Independently timestamp genuine historical news first-seen (SEC/GDELT) and FOMC/CPI consensus vintages before news alpha, with explicit future holdout.
4. Complete genuinely prospective Paper months with immutable production signals, not mined 2010–2026 data.

Frozen StockLens 8.0 was NOT modified; no synthetic ETF return, automatic trading, strategy promotion, or authorized capital deployment.
