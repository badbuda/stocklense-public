# SL9-023 — Close old PR #2 and #5 outstanding concrete bugs
Date 2026-10-11, preregistered before CI. Keep frozen 8.0 unchanged.
Merge only new relevant methods into current main.
1. Monthly inflows exclude external cash from per-session TWR NAV drawdowns.
   Retain raw NAV DD separately. Require zero deposit path parity.
2. Exhaustively sampled overlapping real QQQ/TQQQ NAV windows 21/63/252/756/1260,
   0 deposits; 3x3 lag 0/1/2 by side slip 10/25/50bp with 2bp fees.
3. AWS DynamoDB archival signal SHA, UTC chronology, 8.0 frozen schema,
   weights, disabled broker actions. Keep prior exchange calendar guard and
   separate paper audit. Read-only; cannot claim AWS actual data audit succeeded
   without scheduling and reviewing a live AWS read-only job.
4. No real money, no new alpha, no synthetic TQQQ, no auto promotion.
One bundled Fast Guard and archived audit; close old PRs after green.
