# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** 2026-11-24  
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

- QQQ adjusted close: **638.1000**
- SMA50: **708.4208**
- SMA200: **682.4213**
- VOL20 annualized: **47.88%**
- MOM12: **8.65%**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: 4755
- First date: 2008-01-02
- Last date: 2026-11-24
- Source: QQQ adjusted daily data
- Raw last date: 2026-11-24
- Last completed date used: 2026-11-24
- Dropped incomplete current session: **False**
- NY validation time: 2026-11-25T00:42:03.613543-05:00
