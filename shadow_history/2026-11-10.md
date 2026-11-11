# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** 2026-11-10  
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

- QQQ adjusted close: **674.7600**
- SMA50: **719.1964**
- SMA200: **680.3452**
- VOL20 annualized: **35.34%**
- MOM12: **11.18%**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: 4745
- First date: 2008-01-02
- Last date: 2026-11-10
- Source: QQQ adjusted daily data
- Raw last date: 2026-11-10
- Last completed date used: 2026-11-10
- Dropped incomplete current session: **False**
- NY validation time: 2026-11-10T21:59:41.421676-05:00
