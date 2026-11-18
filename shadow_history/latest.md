# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** 2026-11-17  
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

- QQQ adjusted close: **656.9500**
- SMA50: **715.3762**
- SMA200: **681.5753**
- VOL20 annualized: **36.04%**
- MOM12: **8.41%**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: 4750
- First date: 2008-01-02
- Last date: 2026-11-17
- Source: QQQ adjusted daily data
- Raw last date: 2026-11-17
- Last completed date used: 2026-11-17
- Dropped incomplete current session: **False**
- NY validation time: 2026-11-17T23:38:14.425522-05:00
