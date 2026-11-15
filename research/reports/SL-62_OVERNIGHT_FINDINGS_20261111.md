# SL-62 — Overnight vs Intraday: preliminary cost-aware findings
Date: 2026-11-11

**RESEARCH ONLY. Frozen StockLens 8.0 unchanged. No AWS deploy, no broker execution or production promotion.**

## Input / experiment

* Fixed observed Yahoo auto-adjusted daily QQQ/TQQQ Open and Close, 4,191 sessions, 2010-02-11—2026-10-09.
* Source snapshot SHA256: bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129.
* $100,000 modeled inception capital, no contributions, cash constrained, whole shares, no leverage over the frozen 8.0 target.
* Exact prior-session StockLens exposure labels: 0x, 1.25x, 2x, 3x. Overnight is prior CLOSE to following OPEN, not an observed MOC/MOO brokerage fill.
* Three friction models **per side**: zero for nontradable ideal reference, 2 bps commission + 5 bps slippage, 2 bps commission + 10 bps slippage.
* The simulation validates the full frozen daily NAV curve against the published original offline proxy to sub-floating-point tolerances.
* Night-20 means retain 100% of frozen overnight target but only 80% during regular trading hours; night-50 is analogous. Both require two exposure changes per day. Day-20/50 reduce overnight target instead. Flat-20 is a constant risk-reduction control, NOT a trading-timing winner.
* Annualized CAGR uses start/end calendar time. MaxDD is on daily marked closing NAV.

## Full historical results — before Israeli capital-gains tax

| Strategy | Gross CAGR | 2+5 bps CAGR | 2+10 bps CAGR | Modeled MaxDD | Modeled order count |
|---|---:|---:|---:|---:|---:|
| Frozen 8.0 unchanged | 40.95% | 40.41% | **40.03%** | -49.08% | 147 |
| StockLens Overnight only | 38.10% | -0.14% | **-20.59%** | -98.14% | 8,899 |
| StockLens Intraday only | 2.28% | -25.76% | -35.85% | -99.96% | 7,964 |
| Frozen with daytime exposure -20% | **42.21%** | 32.87% | 26.57% | -51.17% | 8,942 |
| Frozen with daytime exposure -50% | **42.15%** | 20.67% | 7.34% | -54.90% | 8,942 |
| Frozen with overnight exposure -20% | 33.30% | 24.55% | 18.65% | -48.61% | 8,942 |
| Frozen with overnight exposure -50% | 21.45% | 3.09% | -8.31% | -87.88% | 8,941 |
| Frozen with 20% lower exposure always | 34.25% | 33.84% | 33.54% | -45.28% | 147 |
| QQQ Overnight only | 12.80% | -19.97% | -29.79% | -99.72% | 6,502 |
| QQQ Intraday only | 5.91% | -23.82% | -30.06% | -99.75% | 5,864 |
| TQQQ Overnight only | 33.36% | -5.74% | -26.35% | -99.49% | 8,381 |
| TQQQ Intraday only | 7.49% | -23.93% | -36.96% | -99.97% | 7,794 |

## Interpretation

The gross overnight component historically dominated the gross intraday component, but this does NOT imply daily close-buy/open-sell can outperform after costs. The 2+10 bps per-side research model makes thousands of two-way transactions extremely damaging. Even the seemingly attractive gross 20% day-exposure cut was materially worse than the frozen baseline after modeled costs.

An efficient proposal would need to be **sparse and event-driven**, not a daily rebalance, with strict prior-available signals, risk-matched comparisons, counterfactual costs, and independent prospective validation. There is no winning challenger to promote here.

## What this does *not* prove

1. US closing and opening auction prices are NOT guaranteed fills; daily adjusted OHLC cannot measure 09:31/09:32/09:45/10:00 execution or bid/ask spread.
2. Research tax-lot FIFO/FX modeling was NOT applied. Repeated realized gains, minimum commissions and Israeli withholding would further change results.
3. The 2010–2026 snapshot was already used to shape StockLens. This is NOT an untouched OOS test or evidence of statistical significance.
4. 1986–2010 TQQQ prices do not exist. Any older backtest requires separately labeled synthetic assumptions.
5. No after-tax CAGR is claimed and none of these outcomes should be interpreted as a trading recommendation.

## Reproduction and gates

Implementation: research/overnight_session_timing_study.py
Tests: tests/test_sl62_overnight_session_timing.py
Offline CI: .github/workflows/sl62-overnight-research.yml

Run:
    python -m unittest discover -s tests -p test_sl62_overnight_session_timing.py -v
    python -m research.overnight_session_timing_study

Issue SL-62; next separate study should examine sparse execution schedules and minute/auction evidence without modifying the frozen model. No PROD/ST Paper mutation permitted.
