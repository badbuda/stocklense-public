# StockLens 8.0 — Predeclared ML return-enhancement research charter (2026-10-10)

## Thesis and scope

Assess whether deterministic causal machine learning adds **geometric portfolio return** to frozen 8.0 after modeled whole-share ETF trading fees and time delays. ML must neither modify StockLens core logic nor authorize actual broker orders. Previous Vol60, VIX, credit, breadth, term structure and momentum overlays largely failed robust improvement screens. Historical 2018–2026 has already been repeatedly studied and **IS NOT a pristine independent holdout**, regardless of monthly walk-forward mechanics.

## Fixed hypothesis family (declared before the CI research outcome)

Estimator: standardized NumPy linear ridge with unpenalized intercept, fixed 20.0 L2 penalty; last 756 mature labels, refit first trading session each month, no random search or hyperparameter tuning. Input to OPEN day t uses ONLY historical close/open observations through session t−1: QQQ 5/20/63 log momentum, realized vol20/63, distance to SMA200, 63-day drawdown, TQQQ minus QQQ 20-day momentum, and average last-five observed QQQ overnight open gaps.

Target: log real observed TQQQ adjusted CLOSE at t+4 divided by TQQQ adjusted OPEN at t, minus log equivalent QQQ return. Every five-day label must have fully matured before model fitting, plus a full FIVE-session embargo. Models retrain monthly from past only; 2018–22 and 2023–26 report historically reused walk-forward evaluation, NOT untouched source-era testing. Overlapping labels cannot justify iid p-values.

Comparisons: frozen baseline; ml_ups (predict >+0.005 -> one tier higher), ml_down (predict <−0.005 -> one tier lower), ml_both (both), and a simple no-ML control that upshifts if previous 20 QQQ sessions gained over 5% and realized vol20 under 28%. Frozen 0x defense is inviolable; max permitted effective leverage 3x, otherwise frozen.

One entire portfolio engine, same observed Yahoo-adjusted REAL QQQ and REAL TQQQ daily OPEN/CLOSE (not synthetic 3x QQQ), 2bp fee per side and 10/20/30bp hypothetical slippage per side. Evaluate two additional decision lags (0/1), five variants: 30 predeclared mode/lag/cost accounts. Verify baseline daily NAV EXACTLY equals the older frozen same-source whole-share engine before any comparison. Test 2018–2026 on one uninterrupted portfolio NAV curve, with two historical sub-era views without resetting NAV.

Historical continuation gate, not investability: at least +1 annual CAGR percentage point vs frozen on all four lag0/1 by slippage10/20 scenarios; full MaxDD deterioration no worse than 1pp in any case; positive CAGR delta within both previously reused eras, AND positive R² on five-day excess outcome vs training-mean-only predictions within both eras. Even satisfying all conditions **never** changes a live order or model.

Strict source restrictions: no leaked same-day close into order features; no future label maturity; no global feature mean/scaling; no lookahead in positional features; no user-side after-outcome threshold adjustment; no source substitution or retrospective present-constituent breadth. Fit provenance and source digest must be included with numeric outputs. The model is a research diagnostic, with no independent bid/ask or actual 09:31/09:32 executions.

If the model fails, record the negative result and STOP mining slight variants of this same historical sample. Next distinct data hypotheses would require point-in-time index breadth/constituent membership, timestamped auction/venue fill and liquidity spreads, option term-structure data revision histories, or cross-market transfer; until then XGBoost/deep learning is not automatically a stronger investment strategy.

Research script: observed_etf_causal_ml_meta_leverage.py. Original frozen 8.0 unchanged; no authorized capital deployment.
