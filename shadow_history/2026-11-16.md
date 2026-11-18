# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** 2026-11-16  
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

- QQQ adjusted close: **661.7500**
- SMA50: **716.5894**
- SMA200: **681.4106**
- VOL20 annualized: **36.03%**
- MOM12: **9.28%**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: 4749
- First date: 2008-01-02
- Last date: 2026-11-16
- Source: QQQ adjusted daily data
- Raw last date: 2026-11-16
- Last completed date used: 2026-11-16
- Dropped incomplete current session: **False**
- NY validation time: 2026-11-17T00:17:38.492706-05:00
