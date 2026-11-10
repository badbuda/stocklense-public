# StockLens parallel challenger screen — 2026-11-10

**Status:** historical exploratory batch completed, no promotion, no broker orders, no PROD/ST mutation. All metrics are **pre-tax** and not a forecast. The data snapshot ends **2026-10-09** (not current market data).

## Shared evidence / frozen-baseline parity
- Source: `research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json`, SHA256 label `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`
- Observed adjusted daily **QQQ and TQQQ** OHLC, Yahoo historical capture; no synthetic pre-2010 TQQQ in this comparison.
- Common warm-start date **2010-11-26**, last **2026-10-09**, **3,991 sessions**; initial $100,000, no external contributions, zero cash yield, 98.5% risk-on invested.
- Simulated **next-session adjusted daily OPEN**, whole shares, 2 bps fee and 10 bps slippage **each side**. Not broker fills and not exact frozen 09:31/09:32 execution.
- Full-available-history frozen 8.0 replay independent ledger check: `$27,256,917.951653548`, **147 trades** versus archived `$27,256,917.951654`, **147 trades**; absolute error below 1 cent. Shared-window metrics below use the common warm-start date.

## Same-window performance (pre-tax)

| Strategy | CAGR | MaxDD | Trades | Terminal equity |
|---|---:|---:|---:|---:|
| QQQ buy/hold | 19.13% | -35.06% | 1 | $1,608,355 |
| TQQQ buy/hold | 41.30% | -81.65% | 1 | $24,137,477 |
| StockLens 8.0 frozen | 39.84% | -49.08% | 127 | $20,454,350 |
| LRS SMA200 QQQ-close cash/TQQQ | 29.17% | -59.90% | 87 | $5,805,755 |
| LRS SMA200 with 1%-band on QQQ | 31.94% | -58.35% | 39 | $8,136,694 |
| QQQ RSI7 risk-cap exploratory | 37.23% | -48.15% | 281 | $15,170,429 |
| Autopilot **loose proxy** | 4.45% | -30.01% | 206 | $199,678 |
| Autopilot **stricter proxy** | 2.08% | -27.25% | 144 | $138,592 |

**Do not equate the Autopilot proxy with the creator's actual system.** The video lacks exact TSI settings, support/reversal criteria, and partial exit percentages; these were not recoverable from the transcript. The proxies only test disclosed ingredients with explicitly chosen interpretation. Their results cannot prove or disprove the claimed +168% during 2024.

## Additional period diagnostics
- 2022 return: QQQ -32.52%, TQQQ -79.08%, Frozen -44.32%, LRS -44.51%, LRS band -35.24%, RSI proxy -37.10%, Autopilot loose proxy -5.64%, stricter proxy -5.64%.
- 2024 return: QQQ +25.54%, TQQQ +58.26%, Frozen +57.94%, LRS +57.92%, LRS band +57.91%, RSI proxy +48.24%, Autopilot loose proxy -3.03%, stricter proxy -12.75%.
- Autopilot proxy entry counts: loose 92 over full window, stricter 65; mean holding of completed trades about 6.3/6.1 trading sessions, respectively. These counts are incompatible with the claimed 4-6 annual opportunities because the exact creator's reversal definition was unavailable.

## Method details and limitations
1. LRS uses **previous completed QQQ close** against its previous 200-session mean; it is a QQQ approximation to underlying Nasdaq-100 index signals, not exact NDX values.
2. 1%-band LRS stays risk-on until previous completed close < 99% of SMA200 and stays cash until close >101% SMA200. No look-ahead into execution OPEN.
3. RSI7 exploratory cap: previous-session QQQ RSI7 below 25 caps the StockLens target to 1.25x; otherwise frozen target unchanged. This is *not* Nasdaq breadth and does not constitute validated alpha. Parameters were not sealed as pristine OOS.
4. Autopilot proxies use TQQQ EMA8 upward crossing, an EMA-based TSI positive vs signal, QQQ above SMA200, approximate +10%/+20% partial exits, and a 5% stop evaluated on previous daily CLOSE then executed next OPEN. The stricter proxy additionally requires TSI > 0 at entry and exits on TSI weakness. No intraday high/low stop fills or creator's unspecified support signal are recreated.
5. Breadth/%Nasdaq-100-above-SMA50 and Bullish Percent Index **NOT RUN:** no point-in-time index-membership/individual-stock history validated in this snapshot. Do not fill values with today's members (survivorship bias), do not call RSI a breadth backtest.
6. **Israeli tax not modeled.** Reliable cost basis, historical NIS FX, FIFO and broker-specific withholding/tax timing required; transaction counts and gross outcomes are not after-tax performance.
7. All variants reuse previously studied 2010–2026 history; this is an **in-sample exploratory comparison**, not pristine forward test. Overfitting, signal snooping, data-vendor parity and regime stability still require evaluation.
8. Frozen baseline was never edited; no automatic strategy promotion or capital deployment.

## Research decision
- **LRS** fails to beat frozen StockLens 8.0 on this shared history for either CAGR or MaxDD; no promotion.
- **RSI7 risk-cap** marginally reduces MaxDD (~0.93 percentage points) but reduces CAGR (~2.61 points), with high turnover; no promotion.
- **Autopilot proxy** has insufficient specification to make claims about the published system. Need complete trade log, executable entry/exit rules, and actual stop behavior; do not promote.
- **Market Breadth** requires point-in-time constituent dataset before testing; mark BLOCKED_DATA instead of inventing historical signals.
- Next independent check: run both base and challengers in repository CI, reproduce daily paths and costs; maintain forward-only research registry, stress and after-tax scenarios separately.

Related Jira: [SL-58](https://bareketumiel.atlassian.net/browse/SL-58), [SL-59](https://bareketumiel.atlassian.net/browse/SL-59), [SL-60](https://bareketumiel.atlassian.net/browse/SL-60).
