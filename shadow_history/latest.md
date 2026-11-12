# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** 2026-11-11  
**Action:** REBALANCE_NEXT_SESSION  
**Changed vs prior session:** YES

## Current state

- Level: **2**
- Defense: **OFF**
- Target leverage: **2.00x**
- QQQ target weight: **49.25%**
- TQQQ target weight: **49.25%**
- Cash / buffer: **1.50%**

## Features

- QQQ adjusted close: **690.3800**
- SMA50: **718.8660**
- SMA200: **680.6522**
- VOL20 annualized: **36.18%**
- MOM12: **11.29%**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: 4746
- First date: 2008-01-02
- Last date: 2026-11-11
- Source: QQQ adjusted daily data
- Raw last date: 2026-11-11
- Last completed date used: 2026-11-11
- Dropped incomplete current session: **False**
- NY validation time: 2026-11-11T23:03:44.674194-05:00
