# SL9-014 — Historical effective-date EFFR cash sensitivity and predeclared crisis diagnostics
Date: 2026-10-11. RESEARCH ONLY. Reuse old stocklens8 QQQ/TQQQ as-is and
source-pinned real adjusted GLD/TLT from original 2026-10-11 acquisition run.

Research asks:
1. Quantify hypothetical cash credit on idle *modeled* whole-share account
using genuine NY Fed EFFR **effective dates**, with a conservative assumed
two-completed-XNYS-session information lag (no provider first-seen proof), for
zero benchmark cash, EFFR-200bps, EFFR-100bps and EFFR benchmark. Apply
calendar-day compounding to PRE-OPEN cash only before each open. This is NOT
a historical broker swept deposit yield, fund return, independently
timestamp-certified vintage or actual after-tax currency-adjusted performance.
The two initial days have zero modeled credit due to missing warmup quotes.
Reject stale, malformed, duplicate or unverified rate sources; never invent
historical availability timestamps.
2. Audit historical downside and crisis endpoint returns for previously tested
fixed 100/0/0, 85/7.5/7.5, 70/15/15 frozen/GLD/TLT accounts, without adjusting
weights. Pre-specified windows: 2015-07-20--2016-06-27,
2020-02-19--2020-03-16, 2021-11-19--2022-05-06 and
2018-10-01--2019-01-02; pre-specified eras 2010-17, 2018-22, 2023-26.
Daily whole-share simulated NAV, no price interpolation or synthetic ETF.

Inputs: GLD/TLT SHA256 `2f680455c1ba81eb2e859eb9520efb2c1139d2e2861ba715c697712004ee2210`;
QQQ/TQQQ SHA256 `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
EFFR original effective-date JSON from official New York Fed API artifact
https://github.com/badbuda/stocklense-public/actions/runs/38108795287

One PR, one CI; restore same source archive by run-id, never quietly
refetch historic data. Fail CI on missing source archive. Daily frozen
NAV must equal prior whole-share baseline when cash interest is zero.
A result, positive or negative, cannot change production StockLens 8.0,
authorize broker trading, imply verified provider timestamp, or promote a model.
Historical 2010–2026 sample repeatedly reused, not a pristine OOS holdout.
