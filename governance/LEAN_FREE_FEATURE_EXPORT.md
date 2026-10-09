# P0: LEAN feature export on QuantConnect Free — no Object Store download

The repo already contains the original SL724 observer-only Object Store exporter, but non-permissioned accounts may **not** be allowed to download Object Store outputs. QuantConnect documents that Download Results can carry plotted values, with **10 custom series and 4,000 points per series on Free**: https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results

The frozen original SL724 chart already has **3** series: Leverage, NAV and Drawdown, with **3,774** points each. The diagnostic observer adds exactly **7** series on **SL724_P0_FEATURES**: close, sma50, sma200, vol20, mom12, level, defense. There are no artificial missing-day fillers. **Caution:** review any OTHER user-created plot series in the copied QC algorithm first; if more are present, the total may exceed Free's series limit. LEAN engine/library charts and platform limits can change.

## 1. Instrument a private COPY of original LEAN source

Add `integrations/lean_chart_feature_exporter.py` to the copied QC project. In `initialize` / `Initialize`:

```python
from lean_chart_feature_exporter import LeanChartFeatureExporter
self._sl_p0_export = LeanChartFeatureExporter()
```

At the exact point the original algorithm **has already computed and committed** each decision using its own native source data (once per real decision session, not hourly):

```python
self._sl_p0_export.record(
    self,
    close=close, sma50=sma50, sma200=sma200,
    vol20=vol20, mom12=mom12, level=level, defense=defense
)
```

These variables are **illustrative** and must be mapped to the native LEAN variables in the original project, not invented or recomputed from Yahoo. It does not recalculate or change orders and is not an alternate strategy.

Do not replace the current 8.0 source, edit decision rules, or introduce extra chart series.

## 2. Run once and download QuantConnect backtest Results JSON

Keep the exact original frozen trading start/end, fees, security data modes, adjustment settings, universe and warmup. Download the FULL backtest results. Check the original `SL724` Leverage series still has **3,774 aligned entries**, same date and leverage day-by-day as original `Determined Red Orange Duck.json` (the original source SHA is pinned in `qc_original_lean_chart_audit.py`). If not, stop; do NOT try to engineer indicator inputs backwards.

In your local StockLens repo, with the original JSON kept outside the public repository:

```bash
python qc_chart_feature_acquisition.py \
  --original "/private/Determined Red Orange Duck.json" \
  --diagnostic "/private/SL724 P0 diagnostic Download Results.json" \
  --out governance/qc_lean_daily_features.csv \
  --audit research/local/lean_chart_transport_audit.json
python qc_same_input_parity.py
python qc_parity_dossier.py
```

The importer compares **all 3,774 session dates and leverage decisions** to the original LEAN reference before accepting input; any truncation, missing series, changed original decisions, NaN or illegal level aborts. `qc_input_ingestion.py` then validates the original golden transition hash/distribution.

## 3. Critical distinctions

The QuantConnect chart exporter might round numerical feature values and a new run may receive revised historical vendor data. Thus passing the chart output gate **does not** prove bit-exact original native indicator values or that the source code was identical to the original frozen backtest. The report says `native_feature_serialization_exact_precision_proven=false` and `native_algorithm_source_identity_proven=false` until separately verified, and `FULL_SAME_INPUT_PARITY_PROVEN` stays blocked.

The data-only diagnostic allows us to locate the first diverging `level`, `defense`, `leverage` or threshold inputs. If QC cloud quota or native file restrictions prevent this extraction, stop and retain the gate; no synthetic substitute is permitted.

**No QuantConnect run was initiated by this code.** The user must have access to the original private QC source and account to run the observational diagnostic. Nothing gets deployed to a real broker.
