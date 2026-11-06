# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** 2026-11-05  
**Action:** REBALANCE_NEXT_SESSION  
**Changed vs prior session:** YES

## Current state

- Level: **1**
- Defense: **OFF**
- Target leverage: **1.25x**
- QQQ target weight: **86.19%**
- TQQQ target weight: **12.31%**
- Cash / buffer: **1.50%**

## Features

- QQQ adjusted close: **647.0500**
- SMA50: **722.0334**
- SMA200: **679.6072**
- VOL20 annualized: **31.43%**
- MOM12: **4.98%**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: 4742
- First date: 2008-01-02
- Last date: 2026-11-05
- Source: QQQ adjusted daily data
- Raw last date: 2026-11-05
- Last completed date used: 2026-11-05
- Dropped incomplete current session: **False**
- NY validation time: 2026-11-05T22:37:46.095170-05:00
