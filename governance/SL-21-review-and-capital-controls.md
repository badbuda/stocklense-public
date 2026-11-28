# StockLens review and operating controls

## Linking research and changes

Use a branch such as research/SL-51-no-change-cost. Include the Jira key in the commit and PR title, link the Jira issue in the PR, and return the merged commit, passing CI run and evidence path to the issue. Record any input assumptions and unresolved acceptance items there. The author and reviewer alternate between Bareket and Shahar. The other contributor reviews source, tests, and any changes in risk or deployment scope. If that reviewer is unavailable, retain the PR for review. The main-branch protection policy calls for a reviewed PR, a passing Fast Guard for the exact head and disabled force pushes. Repository settings require separate verification. Research PRs do not authorize production changes.

## Real-money decision and stop procedure

The current authorized live order count, single-order notional and account allocation are zero. Before any pilot the account owner records the pilot amount, a maximum order notional, maximum gross exposure, loss budget and daily loss threshold in account currency. Keep the limits at zero until the owner signs the actual numbers, the second reviewer independently checks them, and execution permissions are separately approved. Freeze the model version and its reference data for that decision. Use the prospective and sandbox checks in research/LIVE_TQQQ_READINESS_RUNBOOK.md.

At each session reconcile opening cash and whole shares, the prior session signal, both order timestamps and quantities, fees and closing balances. The operator checks the receipt pair and alarms. A missing or divergent receipt, stale quote, unknown order state, duplicate intent, account mismatch or breached limit halts new submissions. Record outstanding order IDs and independently establish their status with the broker before retrying. Disable the execution route, preserve evidence, reconcile cash and positions, and revert to paper observation. Liquidating positions requires a separate owner decision. Reopening requires incident review, a successful dry run and both approvals. Broker failure harness results are local simulations.
