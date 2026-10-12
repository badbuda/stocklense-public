# Staged independent signal producer

`independent_signal_producer.py` is **not deployed**. It uses the frozen `stocklens.core.replay_levels` directly and does not fetch GitHub. It requires an independently acquired, audited **adjusted QQQ daily CSV** in versioned S3.

Packaging: include `stocklens/core.py` and this handler in a Python 3.12 Lambda ZIP, set handler `independent_signal_producer.handler`, and grant only scoped S3 GetObject/GetObjectVersion for `market/qqq/*` and PutObject for `signals/*`. The S3 bucket must enable Versioning, SSE and Block Public Access. No DynamoDB or broker permissions.

Invocation event must contain `input_key`, `input_version_id`, `expected_input_sha256`, `expected_session`, `independent_provider_verified: true`. This last flag is a *caller assertion*, **not proof** of data independence: do not schedule or deploy before implementing provider ingestion, timestamped provenance, exchange calendar, feature parity, input snapshot manifest and verification. CSV uses Date,Close adjusted series; never substitute unadjusted prices.

Output is immutable `signals/YYYY-MM-DD.json`; it is NOT promoted to `latest` and does not change existing production Lambda, schedule or table. Test parity with frozen `stocklens.shadow.build_report` on the exact same CSV and compare all decision/action fields before activation. The staged producer currently does not include the complete data_audit fingerprint contract and must not be treated as byte-for-byte parity with the legacy report.

No broker calls, no synthesized fills, no direct market-order execution. Do not merge this as production-ready.
