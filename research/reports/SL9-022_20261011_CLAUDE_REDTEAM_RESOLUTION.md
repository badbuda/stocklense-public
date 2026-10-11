# Claude red-team response — StockLens 8.0, SL9-022 evidence, 11 Oct 2026

**Scope:** audit fixes and source archive, NOT a new alpha result. Frozen 8.0 untouched; no capital authorization.

## Disposition of Claude’s findings

| Finding / request | Verified action / status | Remaining limitation |
|---|---|---|
| Original ten SL9-007 simulated-forward rows are identical in economics | Independently read the actual repository CSV. **10 rows**, strategy vs baseline **0 economically distinguishing sessions**, both exposure **3.0x in each**, max absolute return difference ~**2.01e-16**. New fail-closed validator `sl9_022_original_forward_qualification.py` confirms with real repository input. | These original 10 are **NOT proof of either directional superiority or actual forward execution**, even with unchanged CSV rows. |
| Original SL9-007 QQQ return times target leverage | Source `research_data_adapter.py` and `research_upshift_confirmation.py` explicitly labelled `PROXY_NOT_ETF`. Original CSV preserved byte-for-byte; frozen 8.0 and its separately observed QQQ/TQQQ historical account untouched. | Do **not** silently replace this old source or present it as physical TQQQ NAV. New independent frozen-8-forward collector required. |
| Registry fingerprint discrepancy | Stored original registered digest `ffd63bf6988f51442f2ff2232fbace4054b55e88d8afe968e4817759d274897d`; queue digest `995ffc17a889c63d3fcc68376a2b9a688f038c6866820e6baace660e67d02528`; experiment definition digest matches. New `capital_readiness.py` blocks optimistic readiness when evidence digest mismatches and when the original paper evidence is still qualified only as a proxy. | **UNRESOLVED** — cannot declare the two digests equivalent without exact original 4,292-row source and function-byte reconstruction. No fingerprint reset. |
| Capture GitHub-server timestamps before events expire | Bounded official GitHub Events REST pull completed in CI, **3 source pages**, **186 PushEvents** included, each source page SHA-256 recorded. None of three original Git commit SHAs was located in the bounded event list. Events timestamps are GitHub-side but not data-provider first-seen. | No server receipt for the relevant original commits was independently recovered. Absence from bounded latest events does **not** prove absence of original pushes. Raw page bytes were not permanently saved; only page hashes and summary. |
| Preserve expiring Oct 8–10 source artifacts | Downloaded **four original GitHub Actions ZIPs byte-for-byte** using the GitHub connector (CI runner's secondary ZIP retrieval failed HTTP 401). Created a combined ZIP bundle containing original ZIPs, individual ZIP SHA-256, source file digests, and quantitative adjusted-price comparisons. The complete bundle was saved to the user's Files Library as `/StockLens_Claude_RedTeam_Evidence_2026-10-11.zip`, archive SHA-256 `c7922ca6b6b658da36f34c4ce6cd0021041df75470a7fb924ce9f3d3cd9ed971`. | This is original research provenance data, not a permanent WORM independent capture or verified as-of data-vendor receipt. CI artifact mirror from PR #68 did NOT contain the four old ZIPs; the separately saved Library bundle does. |
| Model readiness/forward governance | PR #68 merged after green **554 tests** and explicit original non-discrimination. Qualification is now **0 independently proven observed-real-ETF forward sessions**, not 10. Original data and 8.0 frozen decision logic unmodified. | The next *actual* 63-session program needs real server-received immutable external receipts and different data basis. |
| Historical CAGR discrepancy | Canonical `observed_etf_two_question_audit._metrics` uses `years=(last_date-first_date).days/365.2425`, `CAGR=(ending_NAV/100000)^(1/years)-1`, with initial modeled 100k **before first OPEN trade**; 4,191 observed QQQ/TQQQ open/close sessions. | Another NAV source, cashflow convention, startup NAV, year count or path transformation can yield ~39.5–39.8%; Claude should reconcile *same daily NAV bytes* and starting-equity/date exact before comparing. |

### Original ZIP server metadata and SHA-256 (archive in user Library, originals otherwise expire)

| Artifact ID | Original created_at UTC | Original expires_at UTC | Exact original ZIP SHA-256 |
|---|---|---|---|
| 11530228655 | 2026-10-08 05:33:17 | 2026-11-07 05:33:16 | `478363ba9786f983bdf893bf7e0ac1eed5868ce4e5a99fee7bca13b4aaa6ca67` |
| 11562024976 | 2026-10-08 16:09:15 | 2026-11-07 16:09:14 | `ee86610dc9238becaed6d03bc28252c3ad1aa58fc766e305ee6567fe0912c5b9` |
| 11595483058 | 2026-10-09 04:36:28 | 2026-11-08 04:36:27 | `ea2d38656a7f39973deef30611ad8361052f2b31a857b11df12d348721df3770` |
| 11656109189 | 2026-10-10 02:32:14 | 2026-11-09 02:32:13 | `ec611e440838e1dac3adba96d8551b6b15f8f4127d19ca4181401cbd67cca0fa` |

The above source ZIPs were independently extracted and their member CRC checks passed. Names and exact hashes are in the user's archive manifest.

### Observed QQQ/TQQQ price-source drift, *not* a conclusive SL9-007 source forensics

The Oct 8 end-of-day artifact holds 4,189 observed ETF rows; the Oct 9 archive 4,190; Oct 10 archive 4,191. Compare exact shared trading dates:

| Price-vintage diff | Matched days | QQQ adjusted CLOSE changes (exact float) | TQQQ adjusted CLOSE changes | Maximum relative QQQ CLOSE shift |
|---|---:|---:|---:|---:|
| Oct 8 → Oct 9 | 4,189 | 3,220 | 3,075 | **1.07325565e-6** |
| Oct 9 → Oct 10 | 4,190 | 3,246 | 2,990 | **9.68171679e-7** |

Typically the shifts are only ~1–2e-7 relative. This confirms that a Yahoo-adjusted historical price feed can revise thousands of prior sessions between consecutive daily snapshots; the date coverage also grew by one market session per archive. **It supports the plausibility of Claude's benign source-drift hypothesis but does not prove that these particular 4,189/4,190/4,191 ETF files were the exact 4,292/4,302-row inputs to the disputed SL9-007 SHA digest.** Thus classification remains UNRESOLVED.

### CI details and evidence

- [PR #68](https://github.com/badbuda/stocklense-public/pull/68) merged after [green complete run #38119189832](https://github.com/badbuda/stocklense-public/actions/runs/38119189832): **554 pytest passed**. Previous failed run #38119107728 was a syntax-escaping error in a source metadata patch, fixed before green (the original SHA computation string restored exactly).
- [Source capture result](https://github.com/badbuda/stocklense-public/actions/runs/38119189832/artifacts/11694164795) has full machine-readable SL9-022 qualification and GitHub event page digests. Its ZIP size is small because runner ZIP copy was **BLOCKED_DOWNLOAD HTTP 401**; don't claim otherwise.
- Old original forward CSV, registry and source SHA values **were not altered**.
- [PR #67](https://github.com/badbuda/stocklense-public/pull/67) (SL9-021 one-day VIX/VIX3M prior-close inversion) remains a separate draft with [green CI #38118290769](https://github.com/badbuda/stocklense-public/actions/runs/38118290769), **552 tests passed**, fixed historical challenger **39.1229% CAGR, -48.3905% MaxDD, 0/4 lag/cost continuation gates**. Not a test of Claude's distinct *two-consecutive-session* ratio rule and not promoted.
- No new observed brokerage 09:31/09:32 NBBO quote history, approved Market-On-Open route or broker execution fill was produced.

## Decision on Claude's three research proposals

**H1, vintage-certified HY credit expansion:** **BLOCKED SOURCE.** Before code/trading experiments obtain dated, actually accessible per-business-day historical credit-spread releases and archived first-available vintages, independent access/license and cover every intended old market session. No claim of full FRED/ALFRED history. Predeclare Claude's 20-session change > historical rolling 1,260-session percentile 90 with 2x cap, placebo matching duty cycle, 0/1 lag and fees after proving data.

**H2, two completed days of VIX/VIX3M inversion:** **UNTESTED direct two-day rule.** A related *single-day* threshold (>=1.0, 2x cap) was tested via real Cboe indices and failed. The two-day persistence change was suggested *after* those historical tests, thus testing it on the same history would be exploratory sequential model selection. Require explicit registration, fixed cost/lag and placebo/selection adjustment; do not claim a clean independent trial or futures curve.

**H3, official opening auction / 09:31 NBBO / TWAP:** **BLOCKED EXECUTION DATA AND BROKER ROUTING.** Need permitted Nasdaq official open auction price, historical NBBO bid/ask/size, venue timestamps and confirmed Excellence order support/lead time, independently reconciled fees, fills and spread. The Yahoo minute bar OPEN is not an order quote.

## Prospective 8.0-only 63-session pilot — contract, *NOT deployed*

Per session, build independently received pre-open signal digest from frozen 8.0 SHA and source byte digest; separately preserve vendor response bytes and vendor/collector server timestamp, official settled close and unadjusted corporate actions; book real observed QQQ/TQQQ physical share ledger, broker NBBO and fills as separate optional evidence; use external immutable retention (S3 Object Lock compliance or equivalent), anchored hash-chain/Merkle, signed independent audit receipt; every completed session marked COMPLETE or MISSED, never backfilled. **63 sessions are an operations/completeness milestone, not proof of outperformance.** No AWS immutable bucket or signing provider was provisioned or independently verified in this PR.

**Status:** NO PROVEN NEW ALPHA, NO LIVE CAPITAL APPROVAL, frozen StockLens 8.0 unchanged. Send this report *and the independently saved archive ZIP from Files Library* to Claude for further adversarial review.
