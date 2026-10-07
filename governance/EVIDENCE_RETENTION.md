# StockLens evidence retention policy

Git is the immutable control plane, not the raw-data warehouse.

## Commit to Git
- prospective signal/history and decision journal
- compact paper ledger/trades
- compact health/performance/parity summaries
- one-year replay context used by the dashboard
- generated docs/data.json

## Do not commit
- raw downloaded market data
- minute bars
- full backtest result bundles
- temporary/generated output
- duplicate daily snapshots when a journal/ledger already carries the history

## Hard repository budgets
The CI retention guard fails closed before evidence is committed when:
- any committed generated evidence file exceeds 5 MiB
- total generated evidence under shadow_history/, paper_portfolio/, historical_replay/, docs/data.json exceeds 20 MiB

These are intentionally conservative early-warning limits, not GitHub platform limits.
If a dataset legitimately approaches a budget, migrate it to external object/database storage and keep compact metadata + integrity hashes in Git.

GitHub Actions audit artifacts retain 30 days. They are for debugging/recovery, not permanent storage.
