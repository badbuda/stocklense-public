# StockLens — transition timing & observed equal-weight participation research (2026-11-10)

**Disposition:** historical screens only, NOT promoted. No AWS/ST/PROD mutation, no broker orders, no full author's Autopilot replication.

## Experiment A — 2³ transition timing combinations on frozen 8.0

Frozen 8.0 output is always the starting leverage level (0 / 1.25 / 2 / 3). These experiments modify **when** transitions occur, rather than layering a persistent cap. Existing 0x defense is immutable.

Three PREDECLARED research-rule families (not attributed to the video creator):
1. **Up-confirm:** for a planned exposure increase, wait at most two sessions when QQQ is below EMA20 or MACD(6,13,5) is negative; always accept scheduled downshift/0x defense promptly.
2. **Early rebound:** during a stable 1.25x/2x baseline plateau, permit one temporary level up when prior QQQ is above 1.01×SMA200 and EMA20, MACD histogram positive, RSI7 ≥55, five-session return positive. Up to three days, eight-day cooldown.
3. **Shock pulse:** following previous session QQQ return ≤−2.5% and below EMA20, reduce one exposure level for two sessions, ten-day cooldown.

Frozen real observed adjusted QQQ/TQQQ; same **3,991-session window 2010-11-26 to 2026-10-09**; 100,000 USD initial cash, no contributions, 98.5% risk-on investment, whole shares, prior close decisions filled at next-session adjusted daily OPEN; fees 2 bps plus 10 bps slippage each side (20 bps stress); 0% cash yield; PRE-TAX. Historical period reused in research, not pristine heldout.

Full common-window frozen parity **PASS** with archived 39.8354% CAGR / −49.0762% MaxDD and 127 transactions.

| On-top transition family | CAGR | MaxDD | Trades | Delta CAGR pp | MaxDD benefit pp |
|---|---:|---:|---:|---:|---:|
| Frozen 8.0 | 39.84% | −49.08% | 127 | 0.00 | 0.00 |
| Up-confirm | 38.84% | −49.03% | 119 | −0.99 | +0.04 |
| Early rebound | 39.73% | −49.08% | 143 | −0.10 | 0.00 |
| Both above | 38.92% | −49.03% | 135 | −0.92 | +0.04 |
| **Shock pulse** | **39.00%** | **−46.91%** | **269** | **−0.84** | **+2.16** |
| Up-confirm + shock pulse | 37.98% | −46.46% | 261 | −1.85 | +2.62 |
| Early rebound + shock pulse | 38.90% | −46.91% | 285 | −0.94 | +2.16 |
| All three | 38.06% | −46.46% | 275 | −1.78 | +2.62 |

**Critical stress result: shock pulse is not robust to additional lag.** At baseline execution (prior close → next open), it appears to reduce MaxDD by +2.16pp, but with **one additional session of decision lag** it worsens MaxDD compared with the equivalently delayed frozen baseline by **0.51pp** at 10bps and **1.27pp** at 20bps; CAGR deteriorates by 0.69–1.29pp. Number of trades more than doubles; turnover rises from ~162.6M to ~405.4M modeled USD over the compounded 16-year history. The behavior may also be sensitive to the untested market gap/intraday stop. Reject production promotion.

Early rebound: 39.73% CAGR, barely below frozen baseline; MaxDD unchanged; 16 additional transactions. In the additional-lag stress it showed positive +0.29pp CAGR at 10bps, but the larger result is mixed and the same historical sample is reused. **Not robust proof of alpha.**

Source proof: [CI PASS, artifact](https://github.com/badbuda/stocklense-public/actions/runs/42771438728), [draft PR #172](https://github.com/badbuda/stocklense-public/pull/172). Machine-readable full result [artifact #13742166477](https://github.com/badbuda/stocklense-public/actions/runs/42771438728/artifacts/13742166477).

## Experiment B — QQQE observed participation proxy

Data acquired from historical real adjusted QQQE ETF closes with Yahoo yfinance. QQQE is the Direxion NASDAQ-100 equal-weight index ETF (launched March 21, 2012). **It is NOT Nasdaq-100 % above 50-day SMA / NDXA50R nor a literal point-in-time membership breadth series**. Here QQQE/QQQ relative 20-session return is a participation/concentration *proxy*.

Acquisition: 3,660 real QQQE daily adjusted closes 2012-03-21 to 2026-10-09; observed acquisition SHA256 `c7503719e097df3b88cac9407affdddbf98702bde0c4c3413ffbf0956307776a`, independently audited **NO**. Strict aligned common cohort 3,632 sessions 2012-05-01 to 2026-10-09 (no synthetic prices/no missing day fills).

Predeclared:
- Control: baseline 8.0 at common cohort.
- Rebound-QQQ: same early-rebound rule as above (price-only control).
- Rebound-QQQE: require positive 20-session QQQE relative return versus QQQ in addition to QQQ rebound conditions.
- Confirm-QQQE: delay baseline upshift up to two sessions while previous-session QQQE 20-session relative return versus QQQ is negative.
- Both QQQE conditions.

| On-top rule | CAGR | MaxDD | Trades | CAGR delta pp | MaxDD delta pp |
|---|---:|---:|---:|---:|---:|
| Frozen 8.0 | 41.67% | −49.07% | 103 | 0.00 | 0.00 |
| Early rebound using QQQ only | 41.77% | −49.07% | 119 | +0.10 | 0.00 |
| Early rebound gated by QQQE | 41.27% | −49.07% | 115 | −0.39 | 0.00 |
| Confirmation delay based on QQQE | 40.32% | −49.44% | 103 | −1.35 | −0.37 |
| Both QQQE rules | 39.93% | −49.44% | 115 | −1.73 | −0.37 |

**No demonstrated improvement from this equal-weight participation proxy;** in most cases it underperforms the baseline and fails to protect MaxDD. All four 0/1-session extra lag × 10/20bps slippage stress pairs are included in JSON. An independent vendor comparison has NOT been performed.

Source proof: [CI PASS with observed source](https://github.com/badbuda/stocklense-public/actions/runs/42771995136), [machine-readable results + acquired historical source](https://github.com/badbuda/stocklense-public/actions/runs/42771995136/artifacts/13741549316).

## What has NOT been proven

- Historical `$NDXA50R` authentic constituent breadth and BPI still **BLOCKED** on certified series; never substitute today's NDX members for 2010 constituents.
- Complete Autopilot entries, partial 10%/20% take profits, and intraday 5–7% stop fills NOT reproduced; these are distinct research questions.
- Historical USD/ILS FX, Israeli tax-lot accounting/FIFO and tax timing, and broker execution slippage NOT included; transaction counts here materially change after-tax desirability.
- No pristine forward/holdout after inspecting this entire period, no causal proof from repeated historical hypothesis screens. Results from the shared source are explorations, not eligible for capital deployment.
- All new code is research-only in separate draft PR; frozen 8.0 and PROD are untouched. General CI source-transfer manifest pins exact blob SHA of added code/workflows.

## Decision

**Do not promote any tested challenger.** Shock pulse appears interesting if we ignore delay, but collapses under one extra session of lag and multiplies taxable trades. Early rebound is close to neutral in aggregate and not demonstrated robust. Equal-weight participation gating was negative.

**Next highest-value legitimate evidence:** obtain valid point-in-time `$NDXA50R` from a licensed data source or survivorship-aware constituent histories with delisted prices; externally validate before testing. Instead of trying many new hand-tuned thresholds against the same reused series, register a small family of hypotheses and prove them prospectively in ST. Independently quantify after-tax/FX for any high-turnover candidate. See SL-49, SL-50, SL-51, SL-58/59/60.

