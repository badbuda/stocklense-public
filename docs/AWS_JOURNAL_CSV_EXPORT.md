# AWS DynamoDB journal: downloadable CSV without new AWS permissions

Use **Actions → StockLens AWS DynamoDB CSV Export → Run workflow** on the existing public GitHub repository, or download the artifact from a successful scheduled run after 09:55 UTC Tuesday–Saturday. No AWS console CSV copying or AWS credentials in GitHub are needed: this reuses the existing, tightly scoped DynamoDB **GetItem** read-only OIDC audit role.

The workflow publishes a zipped **stocklens-aws-journal-csv** GitHub Actions artifact with:

- **sessions.csv**: one row per *expected NYSE trading session*; joined archived frozen signal and modeled paper evidence, exposure, level, modeled NAV, cumulative P&L, drawdown, fees, status and source SHA-256 fingerprints.
- **trades.csv**: modeled paper trade receipts per session (not broker fills).
- **summary.json**: counts of PASS/MISSING_SIGNAL/MISSING_PAPER/MISSING_BOTH/INVALID_EVIDENCE, SHA validity, and a no-live-execution notice.

Expected trading dates are derived from the NYSE calendar, skipping weekends and US exchange holidays. Missing or corrupt records remain visible as gaps; they are **never backfilled**, and the export workflow reports failure rather than claiming success when any expected session is missing or corrupt. Even when failing, the workflow uploads any successfully constructed CSV files for review. The date cutoff is the previous New York calendar day; it will **not** generate an entry for an unfinished US trading session.

The default export contains up to 60 recent NYSE sessions starting from the first real paper record on 2026-10-08. On **Run workflow**, choose 15, 30, 60, 90 or 252 sessions. No DynamoDB Scan permission, IAM stack change, scheduled research run or brokerage permission is required. Each day requires only two strongly consistent DynamoDB GetItem reads, and the number of reads grows linearly with the selected window. GitHub artifacts are retained for 30 days (subject to repository policy).

**Security note:** this repository is public. Do not consider exported model signals or paper accounting confidential just because they are inside a GitHub Actions artifact. If confidentiality becomes important, move the export into a private distribution channel and use authenticated website access.

**To view the export:** open the workflow's latest run, find **Artifacts** at the bottom of the run summary, download **stocklens-aws-journal-csv**, unzip and open **sessions.csv** in Excel or Google Sheets. CSV contains raw values; the _pct fields are already percentages, e.g. -2.57 means -2.57%, not -257%.

The export is a historical snapshot for monitoring, not an independently priced broker statement or a live account connection. It does not change CloudFormation or update a website; an AWS Amplify dashboard with a secure read-only API would be a separate deployment.
