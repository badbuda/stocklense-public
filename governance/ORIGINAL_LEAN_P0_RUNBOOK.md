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


## Daily reference hardening (2026-10-09)

Original saved LEAN `SL724` chart contains 3,774 **daily** date/exposure states. A transition-date hash and regime histogram cannot prove the intervening exchange session calendar: for example, a silent missing day within an unchanged 3x run preserves the 67 original regime transitions and all four exposure counts. This is now detected by **two independent pinned daily digests** computed from the owner's original extracted LEAN CSV:

- `daily_date_leverage_sha256=caa10bea0a07f3c5f6f60fef49fa407844da4ce514fa552e5202d6d1d10cefb5`
- `daily_session_dates_sha256=feacf22f410c9f7fcf129b30e91c03c9a924c80e7a2b88dd8839103547adcb08`

The first is SHA256 of `json.dumps([[date, float(leverage)], ...], separators=(",", ":"))` in original dated order, with 3,774 rows. The second hashes the same 3,774 dates joined by a literal newline (no trailing newline). The 3,774-row source CSV was kept in the owner's private Library rather than added to the public GitHub repository. The private original JSON source itself remains pinned to SHA256 `65cb291e6552dc0f86b32106bc3fe3f7a7ed8a127b3d0d6f84a60a8f5800b6f7`.

`qc_original_lean_chart_audit.py` now requires both daily hashes, while `qc_input_ingestion.py` requires any future *candidate LEAN feature export* to have the **exact dated original 3,774 daily exposure states**, in addition to its indicators, levels, defense, count, transition SHA and exposure histogram. The actual LEAN input features and independent native source identity **remain missing**.

### What we already know from the original frozen LEAN charts

These are descriptive historical facts, NOT strategy alpha:

- Original daily exposures: 3x **3,037**, 2x **76**, 1.25x **387**, cash **274** (total **3,774**).
- During 2014 the reference showed **252 / 252 days at 3x**.
- During 2022 the reference showed **174 / 251 days in cash** and **14 / 251 days at 3x**.
- The longest contiguous 3x interval was **664 sessions (2013-01-03 through 2015-08-21)**.
- The longest contiguous cash interval was **212 sessions (2022-05-06 through 2023-03-10)**.

A frequent 3x exposure combined with regime-sensitive de-risking makes daily exposure matching, timing offsets and benchmark risk comparison more important than an index-aligned transition match rate.

### Repeat the cross-provider daily-level diagnostic privately

```bash
python qc_lean_yahoo_daily_exposure_audit.py \
  --original "/private/Determined Red Orange Duck.json" \
  --proxy docs/portal-history.json \
  --out research/local/lean_yahoo_daily_exposure_diagnostic.json
```

This produces same-calendar-session agreement, a trading-session lag profile at ±2 sessions, year-by-year agreement, exposure-confusion counts and the longest mismatched episodes. **The Yahoo daily-open execution proxy's `l` is based on a prior-session signal**, whereas the LEAN reference chart marks its original decision session. A high raw same-day match will be inflated by both systems spending most of the time at 3x; a better match at +1 day is not a model fix or proof of equal inputs. No source-only change authorizes a new trading rule.

Never report `FULL_SAME_INPUT_PARITY_PROVEN` until native LEAN features exist with 3,774 validated dates, model decisions match on identical original inputs, AND evidence provenance is independently attested. An unknown original data source is a blocker, not a green status.

## Independent Yahoo cross-provider exposure audit (9 October 2026)

New frozen result: [research/lean_yahoo_cross_provider_20261009.json](../research/lean_yahoo_cross_provider_20261009.json).

**Precise comparison:** original saved SL724 LEAN per-session *effective leverage* vs. the separately computed Yahoo-Q QQQ/TQQQ **next-open exposure** in `docs/portal-history.json` (snapshot SHA `42732511d81bca12bdc533cc5eac912c69dc637f85c96137861f702be5adb89b`). The Yahoo stream comes from `tradable_tqqq_execution_comparison.py`: `replay_levels` operating on adjusted Yahoo QQQ completed daily closes, followed by a prior-close-next-open ETF execution proxy. `portal_feed.py` serializes each day into `l`. It does not load the original LEAN chart. This is a **cross-provider behavioral comparison**, not same-input parity.

- **3,774 original** LEAN sessions; **4,190 Yahoo** actual ETF-proxy sessions.
- **112 original sessions precede TQQQ inception/first observed ETF session**, so only **3,662** LEAN chart days are comparable (2010-02-11 through 2024-08-29). There are **no missing original session dates within the proxy's compared interval**.
- Daily effective exposure: **3,655 / 3,662 = 99.8088%** same-calendar-date agreement; **7** daily mismatches (6 in 2010, 1 in 2011).
- The non-3x subset also agrees: **732/737 = 99.32%**. The 3x subset agrees on **2,923/2,925 = 99.93%**; original cash days agree **274/274**.
- Frozen original transition `(date, leverage)` pairs inside the Yahoo interval: **66**; Yahoo proxy transition events excluding its initial baseline: **68**; **62** exact original pairs recur in the proxy. The previous **~7.25% transition-index metric** is **not** the fraction of daily LEAN levels that match — it used a different strict index-aligned event comparison / lifecycle replay; avoid conflating them.
- ±1 Yahoo-session shifts are *worse*: lag -1 agrees **3,592/3,661 (98.12%)**, lag +1 **3,593/3,662 (98.12%)**. A uniform one-session offset does not explain the observed differences.
- Complete agreement 2012–August 2024 in the overlapping ETF proxy, **not** LEAN input-feature identity.

The seven disputed dates are 2010-05-19, 2010-05-20, 2010-06-08, 2010-07-15, 2010-07-16, 2010-08-13 and 2011-10-13. The original private LEAN `Determined Red Orange Duck.json` (pinned SHA) and exact daily chart calendar/daily exposures (pinned SHAs) remain separate from the public repo, but their source identities are recorded in the published audit.

### Reproduce without source contamination

With the private original unchanged, and the pinned Yahoo market-price snapshot available:

```bash
python qc_lean_yahoo_daily_exposure_audit.py \
  --original "/private/Determined Red Orange Duck.json" \
  --proxy docs/portal-history.json \
  --out research/local/cross_provider_exposure_reproduced.json
```

If `docs/portal-history.json` has refreshed after the pinned 2026-10-08 snapshot, results may include additional future days beyond the fixed historical overlap but **the original overlap through 2024-08-29 must remain reproducible**. Verify the SHA before comparing a current run to the frozen dated report. This diagnostic does **not** prove native LEAN `close/sma50/sma200/vol20/mom12` input series are identical. That is still blocked until original-chart-derived feature export is obtained. Same model source identity and real broker execution remain unverified.

These results justify moving the original 7.25% index-transition figure out of any "daily model accuracy" dashboard claim; they do NOT justify automated model promotion, real trading or claims of statistically significant alpha.
