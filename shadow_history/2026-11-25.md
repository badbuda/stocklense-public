# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** 2026-11-25  
**Action:** NO_CHANGE  
**Changed vs prior session:** NO

## Current state

- Level: **1**
- Defense: **OFF**
- Target leverage: **1.25x**
- QQQ target weight: **86.19%**
- TQQQ target weight: **12.31%**
- Cash / buffer: **1.50%**

## Features

- QQQ adjusted close: **633.9300**
- SMA50: **707.0197**
- SMA200: **682.5439**
- VOL20 annualized: **47.68%**
- MOM12: **5.25%**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: 4756
- First date: 2008-01-02
- Last date: 2026-11-25
- Source: QQQ adjusted daily data
- Raw last date: 2026-11-25
- Last completed date used: 2026-11-25
- Dropped incomplete current session: **False**
- NY validation time: 2026-11-26T00:18:49.459670-05:00
