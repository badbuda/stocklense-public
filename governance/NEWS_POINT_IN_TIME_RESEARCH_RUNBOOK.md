# StockLens — news and macro events: practical private-data integration guide

## Why this is NOT just a GPT sentiment indicator

StockLens frozen 8.0 uses past QQQ prices/volatility to decide exposure. News can be valuable as an early warning or company-specific catalyst, but a headline's *direction* is not its tradable surprise. A Fed 25bp rate rise can be perceived as dovish when 50bp was expected; a merger headline may already be in the stock's price. This research isolates three clocks: verified event release, provider observed delivery, and earliest tradable market session. Modern LLM classification of past articles is a retrospective tool unless its training/version and observation timing are independently audited.

## Primary sources, no paid API needed to start

- GDELT 2.0 events/GKG: https://gdeltproject.org/data.html ; 15-minute intervals from Feb 2015, multilingual coverage and repeated stories. GKG DATE is when record is monitored, not guaranteed source headline first publication nor the time the file first reached a historical automated client. Coverage prior to 2015 requires a non-equivalent older vintage.
- Federal Reserve FOMC official statements: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm ; each statement may explicitly say 'for release at 2pm ET', but the *actual rate decision* is not known when its date first appears on a public calendar.
- BLS release times CPI/NFP: https://www.bls.gov/schedule/news_release/cpi.htm and https://www.bls.gov/schedule/news_release/empsit.htm ; scheduled 08:30 ET releases require real UTC conversion using America/New_York DST and pre-release consensus to measure surprise.
- St. Louis Fed ALFRED vintages: https://alfred.stlouisfed.org/help/downloaddata ; use ORIGINAL released/revised vintage, never 2026-revised historical data as if reported in 2010. Vintage date alone lacks exact intraday delivery clock.
- SEC EDGAR submissions: https://www.sec.gov/search-filings/edgar-application-programming-interfaces ; official corporate submissions metadata incl. 8-K/10-Q/10-K. A filing does not itself certify an acquisition, earnings surprise or precise source dissemination, and ticker histories require delistings/point-in-time mapping.

## What is now ready in public GitHub

1. `news_event_pit.py` — strict UTC point-in-time event and immutable first-seen receipt contract, macro/corporate classification, pre-announcement consensus guard, no modern LLM backdated forecasts, duplicate syndicated story suppression.
2. `news_provider_adapters.py` — offline GDELT GKG 2.0 v2.1 field adapter and SEC submissions adapter; unverified in their default output until source provenance reviewed.
3. `news_archive_intake.py` — opt-in local CLI for GDELT ZIP or SEC JSON, with bounded HTTPS allowlist for actual GDELT historical 15-minute archived file download. Raw documents/artifacts are PRIVATE; do not commit article bodies or confidential processing.
4. `news_event_study.py` — replay 1/5/21-day observed adjusted QQQ/TQQQ reaction conditioned on true earliest XNYS session following verified observed delivery; only descriptive research. Without verified dated events prints BLOCKED, not a made-up positive CAGR.
5. `research/news_sources_pit_registry.json` — explicit provider readiness, 2009 versus 2015 historical coverage and paid expectation-data gaps.

## Working examples (run outside public CI)

```
python news_archive_intake.py \
  --gdelt-gkg-zip '/private/GDELT_20150301120000.gkg.csv.zip' \
  --out '/private/gdelt_unverified.jsonl'

python news_archive_intake.py \
  --sec-submissions-json '/private/CIK0000320193.json' \
  --cik 0000320193 \
  --out '/private/sec_unverified.jsonl'

python news_event_study.py
```

To run the study on a historical vetted source you must use `news_event_study.build(journal='/private/verified_pit_news.jsonl')`, with every event record including a 64-byte SHA256 hex raw source fingerprint, original story/vendor record ID, publication/first seen/delivery times in offset-aware ISO UTC, archived immutable receipt URI and SHA fingerprint, numeric processing lag and verified absence of later analyst hindsight. Company-scope stories additionally require historical issuer/ticker symbol mapping. Checksums without reconstructable source/receipt bytes are declared metadata, not final independent proof.

## Source and license controls

No full news content is written to the public repository. Check each provider's redistribution, indexing, derived-signal and commercial-use permissions before production. Avoid historical news downloads that cannot reproduce what an actual subscriber could have known then. Never manufacture historical pre-release analyst expectations; if absent, skip a numerical surprise signal.

## Four next measurable hypotheses (when genuine events exist)

(A) Fed surprise versus market-implied expectations; (B) CPI/jobs announcement surprise versus consensus; (C) geopolitical event shock/volume dynamics rather than naive positive-negative headline sentiment; (D) company-specific SEC disclosure versus sector/risk-matched controls. Freeze the four protocols in the predeclaration file, then compare news-only vs price-only vs frozen8 with same costs/latency, 21/63 day block placebo, source availability lag stress, and independently new future paper. No statistical claim from dates previously mined by StockLens.

**Readiness:** News engine and source validation can be green in CI while historical true news alpha remains BLOCKED. No change to frozen 8.0, portfolio executor, AWS or broker authorization.
