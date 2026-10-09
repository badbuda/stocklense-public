# P0 / Original QuantConnect LEAN identity evidence

## What we actually have

The owner retained the original QuantConnect **Download Results** file named `Determined Red Orange Duck.json` from the frozen SL724 run. It was inspected from the owner's file library, not manufactured from Yahoo. Its original file SHA-256 is:

`65cb291e6552dc0f86b32106bc3fe3f7a7ed8a127b3d0d6f84a60a8f5800b6f7`

The SL724 daily **Leverage, NAV, Drawdown** chart yields **3,774** aligned days from 2009-09-01 to 2024-08-29, **67** transitions, the locked transition hash `5561588a3bcd8a416cc13320536d7d3ff51bdb6de418e4f2c31b85eaf2ac745b`, last NAV multiple 134.1824, maximum drawdown -49.69141%, and leverage distribution 3x 3,037; 2x 76; 1.25x 387; cash 274.

**This is original LEAN output — but it is NOT original daily indicator input.** It does not contain original LEAN QQQ close/SMA50/SMA200/VOL20/MOM12 or original intermediate level/defense.

Do not publish the original full results JSON in a public repo unless the owner explicitly approves disclosure. It can remain private; the verification script accepts a local path.

## Reproduce the original evidence validation

With the original JSON in a local working directory, run:

```bash
python qc_original_lean_chart_audit.py \
  --source-json "/private/path/Determined Red Orange Duck.json" \
  --output-csv research/local/lean_original_daily_chart.csv \
  --audit-json research/local/lean_original_daily_audit.json \
  --proxy-json docs/portal-history.json
```

This validates the original **source bytes SHA**, every original chart timestamp and price/level, the 3,774-session chart lengths, the locked LEAN transition dates/hash, daily leverage distribution and original NAV/drawdown endpoints. The optional Yahoo historical comparison is marked `CROSS_PROVIDER_DECISION_VS_PRIOR_SIGNAL_OPEN_EXPOSURE_DIAGNOSTIC_ONLY`; it MUST NOT be treated as same-input equality or Alpha evidence.

The owner's separately extracted `StockLens_LEAN_SL724_original_3774_states.csv` is also retained in their Library. It contains original dates, timestamps, leverage, NAV multiple and drawdown. These same columns can be regenerated from the JSON deterministically with this script; the source JSON is the definitive audit input.

## The actual missing evidence

A **new observational LEAN diagnostic run using the original frozen algorithm and data configuration** must record these exact 9 fields from within each decision, without recomputing them or changing decisions: `date,close,sma50,sma200,vol20,mom12,level,defense,leverage`.

The observational exporter already exists at `integrations/lean_feature_evidence_exporter.py` and the integration instructions are in that module. Run it in a *copy* of the original frozen QuantConnect project, not in the current Python reconstruction. Download its output legally via supported result/serializations, and place it locally in `governance/qc_lean_daily_features.csv`; no Yahoo-derived fill-ins.

Then:

```bash
python qc_input_ingestion.py
python qc_same_input_parity.py
python qc_parity_dossier.py
```

The new input gate refuses:

- anything but 3,774 original LEAN decision sessions, ordered with exact boundary dates
- wrong/nonfinite QQQ close/SMA/vol/momentum, illegal levels or inconsistent effective leverage/defense
- any deviation from original LEAN 67 transitions and 3,774 daily leverage distribution
- duplicate dates, incomplete columns or malformed numeric values

**Proof boundary:** A structurally valid candidate CSV and a Python calculation matching it are not proof it came from the original LEAN run. `source_authenticity_proven` remains false until native provenance of the entire LEAN feature CSV is independently verified. The `qc_parity_dossier` cannot advertise `FULL_SAME_INPUT_PARITY_PROVEN` before that.

The current partial-replication statistic (~7.25% exact transition-index match) is a Yahoo **cross-provider** statistic, not a per-day same-input LEAN-vs-Python identity score. Preserve those labels.

## Why not reconstruct LEAN features from Yahoo?

Feature reconstruction from a different data vendor might be useful for **diagnosing** price adjustment/session/warmup drift. It cannot prove original LEAN input equality; trading rules may match mathematically on a substituted price series while behaving differently on the original. Do not mislabel reverse-engineered data as a native export.

## Safety and operational constraints

- No frozen strategy edit, no live trading and no broker access.
- No automatic acceptance of missing/partial evidence.
- Original full run charts can be verified offline; avoid unnecessary QuantConnect reruns.
- A fresh diagnostic QuantConnect run may differ from the original due to data revisions; require the resulting 3,774 daily leverage states and transitions to reproduce the locked original before drawing conclusions about identity.
- Don't assume the chart-only evidence proves same-input parity, execution slippage parity or statistics.
