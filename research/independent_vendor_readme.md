# Independent QQQ vendor check — diagnostics only

This is the **independent-price evidence** missing from StockLens 8.0. It does not
resolve Yahoo-vs-Yahoo 38-price precision discrepancies automatically, and it
does not authorize production/broker actions.

Alpaca's *Market Data* API supports daily stock bars with
`adjustment=all` for splits, dividends and spin-offs. The configured
market-data subscription must entitle the user to the requested date range and
feed. No market-data keys are committed to GitHub or logged by these scripts.

On a private development host with Python packages from `requirements.txt`,
and an authorized Alpaca Market Data subscription:

```bash
set -euo pipefail
python -m pip install -r requirements.txt

# Type keys into private terminal prompts; neither secret is supplied on CLI.
read -r -s -p "Alpaca data key: " ALPACA_DATA_KEY; echo
read -r -s -p "Alpaca data secret: " ALPACA_DATA_SECRET; echo
export ALPACA_DATA_KEY ALPACA_DATA_SECRET

SESSION=2026-10-16
mkdir -p /tmp/stocklens-independent-audit

python export_frozen_qqq_reference.py \
  --session "$SESSION" \
  --output "/tmp/stocklens-independent-audit/frozen-$SESSION.csv"

python independent_alpaca_evidence.py \
  --session "$SESSION" --feed sip \
  --output "/tmp/stocklens-independent-audit/alpaca-$SESSION.csv"

unset ALPACA_DATA_KEY ALPACA_DATA_SECRET

python infra/aws/second_vendor_parity.py \
  --frozen "/tmp/stocklens-independent-audit/frozen-$SESSION.csv" \
  --independent "/tmp/stocklens-independent-audit/alpaca-$SESSION.csv" \
  --session "$SESSION" --licensed-asof 2026-10-17
```

`--feed iex` is supported but is a different (single-exchange) sample from
consolidated SIP; both require actual market-data access. The request fails
closed on denied/unavailable history, missing latest bar, duplicate days,
insufficient 2008 warmup, calendar mismatch and changed 8.0 decisions.

A `SECOND_VENDOR_POLICY_DIAGNOSTIC_MATCH` is **not** corporate-action
vintage/provenance reconciliation, price-path identity, point-in-time historical
data access, broker-price confirmation or trade promotion. A 38-row
same-Yahoo precision violation remains an outstanding separate finding.

If there is no licensed independent feed, report `NOT_PROVEN`. Never clone
Yahoo into the "independent" CSV. Freeze the two actual raw-source CSV SHA256s
and date-of-download as diagnostic evidence, not as backfilled Paper trades.
