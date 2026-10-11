# SL9-015 — Frozen StockLens 8.0 vs physically observed QLD alternatives

Date: 2026-10-11. **Historical research only; 8.0 unchanged; no capital deployment or automatic promotion.**

## Evidence

- Research pull request (merged): https://github.com/badbuda/stocklense-public/pull/60
- Green complete CI: https://github.com/badbuda/stocklense-public/actions/runs/38109976546
- **517 pytest tests passed**; 8 CI artifacts saved including an actual observed QLD source snapshot, original JSON results and human report: https://github.com/badbuda/stocklense-public/actions/runs/38109976546/artifacts/11691003662 (30-day retention).
- Frozen QQQ/TQQQ snapshot: `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
- **Actual QLD adjusted daily OHLC source SHA-256:** `fbb7045442cb51062e46feada7489a4fca89e5007dd46fb6eac794f6e3f51cb1`. Sourced from Yahoo Finance with auto_adjust=True daily OHLC. **Not synthetic 2x leveraged returns**.
- Fixed sample: 4,191 exchange sessions (2010-02-11 through 2026-10-09). All genuine QQQ, QLD and TQQQ historical observed adjusted daily opens/closes. Actual historical intraday 09:31 fills, broker commission schedule and vendor price-adjustment cross-audit are **not** established.
- Exact baseline whole-share NAV reproduction verified against the prior independent whole-share engine day-by-day, across additional signal delay 0/1 and modeled price slippage 10/20bps per order side; fees 2bps/side.
- No contribution streams; $100k initial modeled capital.

## Fixed experiments preregistered *before* looking at results

1. Original **frozen 8.0**: 2x level buys 50% QQQ/50% TQQQ within its 98.5% invested fraction; frozen decisions untouched.
2. **Real QLD at 2x**: when frozen 8.0 decides level=2, use 98.5% QLD; every other leverage state exactly original.
3. **Real QLD at 1.25x and 2x**: level=1.25 uses 75% QQQ + 25% QLD inside the invested fraction; level=2 uses QLD; 3x remains TQQQ, 0x remains cash.

| Predeclared mode | CAGR | Full-period MaxDD | CAGR vs frozen (pp) | MaxDD benefit (pp) | Continuation stress tests |
|---|---:|---:|---:|---:|---:|
| **Frozen StockLens 8.0** | **40.0263%** | **-49.0756%** | 0 | 0 | baseline |
| Real QLD only at 2x | **39.8182%** | **-49.0756%** | **-0.2081** | **-0.00003** | **0 of 4** |
| Real QLD at 1.25x & 2x | **39.9900%** | **-48.8257%** | **-0.0363** | **+0.2500** | **0 of 4** |

Predeclared *research continuation* gate (not permission to trade) requires **>=+0.50 percentage points CAGR, and no more than 1pp MaxDD deterioration**, in **all four** cost-and-lag cases. Both challengers failed, despite physical QLD portfolio effects that differed from the equal-notional QQQ/TQQQ mix.

QLD targets 2x of NASDAQ-100 performance **for a single day**, not assured 2x over longer intervals; QLD's real price path and embedded running costs therefore matter. ProShares source: https://www.proshares.com/our-etfs/leveraged-and-inverse/QLD .

## Claude hypothesis coverage — triage, not blanket claim of completion

Maintained preregistered inventory in
`research/predeclarations/SL9-015-CLAUDE-HYPOTHESIS-REGISTER.md`.
Distinctions:
- **Tested in current observed ETF frozen framework:** real QQQ/TQQQ baseline, caps/Kelly-like tested variants, 3-session ramps, fast volatility brake, post-drop slow protection, three ML modes, fixed GLD/TLT portfolio sleeves, and now fixed actual QLD substitutions. Not all candidate variants are interchangeable. Many rejected.
- **Partial or conditional only:** official effective-date EFFR cash accounting (NOT actual Excellence cash yield), VIX/volatility term structure and spread overlays from older studies without newly independently qualified PIT histories, funding/fee stress.
- **Unavailable for defensible historical test:** point-in-time survived breadth/constituents; QLD/TQQQ historical NBBO/VWAP minute execution, actual broker fills and spread/capacity; authenticated GDELT/SEC vendor first-seen, pre-FOMC/CPI consensus vintages, event-driven corporate and geopolitics returns; listed historical options with contemporaneous quote spreads.
- **Distinct future study but avoid old-sample curve fitting:** soft threshold changes, alternative SMA window families, yield/credit overlays in a fresh forward prospective sample. They have not been validated by this QLD PR.

## Decision

**Frozen StockLens 8.0 remains the historical-CAGR leader among these prespecified instrument alternatives.** A modest 0.25pp MaxDD improvement and 0.036pp CAGR sacrifice from the second QLD variant do not satisfy even the preregistered minimum incremental growth. These are reused historic outcomes, not new clean OOS alpha. Do NOT automatically promote a rule, place broker orders, or claim future return certainty.

Next: independent broker cash terms, original 09:31 executable quotes, independently sourced and adjusted ETF pricing, forward prospective paper/holdout, trustworthy first-available macro/SEC/GDELT data. Preserve tight, preregistered experimental families and minimize CI spend.
