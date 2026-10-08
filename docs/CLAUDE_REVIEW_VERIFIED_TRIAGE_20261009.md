# StockLens — independent Claude review triage (2026-10-09)

Source: Claude review supplied by the user on 2026-10-08; compared against current code in badbuda/stocklense-public. Assessment is not an AWS runtime inspection.

| Finding | Verified against repository? | Current action |
| --- | --- | --- |
| H8 generic backtest cashflow-biased daily returns and drawdown | CONFIRMED in backtest_engine.py | Fixed in this PR: time-weighted return index/volatility/drawdown; prior raw-NAV drawdown retained as legacy diagnostic. Frozen 8.0 historical observed-ETF results untouched. |
| H6 lookahead in FrozenExposureReplayAdapter | NOT REPRODUCED: adapter reads previous[leverage] | Regression perturbing *current* fields confirms prior-only applied exposure. Generic StrategyAdapter allows current-dependent strategies; a future general-enforcement contract is still required. |
| H2 duplicate AWS archive falsely succeeds without examining changed hash | CONFIRMED in both AWS Lambdas | Use DynamoDB conditional PutItem ReturnValuesOnConditionCheckFailure ALL_OLD; identical SHA permitted, missing or divergent old item raises error. Requires a CloudFormation UPDATE; NOT DEPLOYED by GitHub merge. |
| H1 CloudWatch alarms do not deliver notifications | CONFIRMED: no AlarmActions | Optional AlertEmail CloudFormation parameter creates SNS topic+email subscription; confirmation required to activate delivery. No email or topic unless configured. Both Lambda alarms connected if configured. Still need an independent missed-invocation heartbeat alarm. |
| C1 independent price verification / immutable provenance | CONFIRMED NOT SATISFIED: Lambda trusts GitHub-published paper ledger, file labels, and internally generated audit | Still BLOCKED. Conditional write and matching SHA detect drift, not vendor-price authenticity or a compromised writer. Need S3 Object Lock, independently sourced quote snapshots, pinned commit SHA, broker quotes and independent NAV computation. Do not call the current data independent verified evidence. |
| C2 observed Yahoo minute-bar open is not a broker fill | CONFIRMED: paper model reads observed 09:31/09:32 bar OPEN and applies modeled 2bps fee/10bps slippage | Still MODEL ONLY. No spread/bid/ask or partial fills; no account cash settlement proof. |
| H4 growing 200k paper ledger and H5 schedules | CONFIRMED 200001-byte paper handler limit and conditional failure | OPEN: move to immutable per-session source files and pin provenance; holidays and delayed GitHub publishing need calendar-aware scheduler and tested recovery. |
| H7 historical close-to-close vs prospective open+2-minute | CONFIRMED different semantics. backtest_paper_gap.py documents gap | OPEN until paired true forward paper sessions; never call replay execution parity. |
| C3 multiple testing and independent holdout | NOT ESTABLISHED; many experiments on same history | OPEN selection bias disclosure, registered new forward experiment and block-bootstrap. Paper execution tests do not prove investment alpha. |
| OIDC trust | VERIFIED IN SOURCE: owner/repository immutable IDs and ref main; aud sts.amazonaws.com | Prior GitHub AWS preflight passed. This is NOT a permission to trade or deploy. |

## Next deployment gate
Existing AWS stack was reported by user as UPDATE_COMPLETE before this PR. This PR MODIFIES CloudFormation, and the changed Lambda code and conditional SNS configuration are NOT deployed until the user explicitly performs another CloudFormation Update (same stack, Frankfurt). If the user supplies optional AlertEmail in the stack parameters, they must confirm the SNS subscription from their inbox. Retention changes from 7 to 30 days and may increase CloudWatch cost.

## Next quantitative and live-readiness gate
- Report observed real QQQ/TQQQ ETF data (never synthetic TQQQ) and frozen 8.0 separately from generic research replay.
- Read account data through an officially documented broker API or authorized read-only CSV export. Do not put broker credentials in GitHub or chat.
- Require prospective quote evidence with bid/ask, order timestamps, fees, and independent reconciliation.
- Reject automatic promotion to live trading. Zero observed frozen paper sessions remains NO-GO.

## Limits of this change
CI unit tests are not AWS runtime proofs. This PR does not deploy AWS, configure a verified SNS email, capture independent quotes, avoid every calendar failure, prove TQQQ profits, or authorize money movement.
