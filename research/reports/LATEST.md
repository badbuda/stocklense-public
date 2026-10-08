# StockLens Research — Latest Human Report

Generated: 2026-10-08T09:29:31.689791+00:00

## שורה תחתונה
StockLens 8.0 נשאר קפוא ולא שונה. אין קידום אוטומטי של אף challenger.

## מצב אימות נוכחי
- Prove-or-Break: 12/12 retrospective checks PASS; prospective=WAITING.
- Historical LEAN evidence: 3774 sessions; MaxDD -49.69141%; NAV multiple 134.1824.
- Canonical historical CAGR: BLOCKED_PENDING_FULL_LEAN_EXPORT; אין להסיק CAGR מה-screenshot.
- Latest publication gate: UNKNOWN.

## מחקר פעיל
- **SL9-007-UPSHIFT-CONFIRMATION** — PREDECLARED_OBJECTIVE_MET_NOT_PROMOTED.
  Holdout: excess CAGR 0.80%; MaxDD -41.66%; improvement vs baseline 2.15%.
  Prospective tracking inception: 2026-09-26; כרגע 8 sessions עתידיים אמיתיים. רק completed XNYS sessions עם date > inception נספרים; אין backfill של יום ה-inception או קודם ואין pre-close ingest.
  חשוב: היעד המוגדר מראש עשוי לעבור, אבל robustness מלא עדיין לא עבר ולכן אין promotion.

## ניסויים שנסגרו
- **SL9-001-VOLATILITY-GATE** — REJECTED: Global volatility-gate thesis remains rejected; do not retune against validation/holdout.
- **SL9-003-STRESS-ONLY** — INVALID_DUPLICATE: Canonical implementation/evidence duplicates SL9-001; not independent confirmation.
- **SL9-004-STRESS-TREND** — NOT_VALIDATED: Development neutral; validation excess CAGR 0.00966613144319628; holdout neutral; walk-forward positive 1/14; bootstrap probability_positive 0.641.
- **SL9-005-DRAWDOWN-BREAKER** — REJECTED: Development/validation neutral; holdout excess CAGR -0.07660720177740421; walk-forward positive 0/14; bootstrap probability_positive 0.0.
- **SL9-006-MOMENTUM-ACCELERATION** — REJECTED_PREDECLARED_RULE: Predeclared sealed-evidence rejection: EXCESS_CAGR_RULE_FAILED; excess_cagr=-6.439293542825908e-15; drawdown_delta=0.0.

## מה המערכת עושה עכשיו
- EPIC-01: keep atomic validated publication green and make generated-report freshness source-SHA aware
- EPIC-02: obtain the same-run 3,774-row + 345-order raw LEAN export required for canonical CAGR and full input parity; never synthesize it
- EPIC-03: accumulate strict post-inception SL9-007 prospective evidence with zero backfill and no automatic promotion
- EPIC-04: deepen execution-reality evidence using costs, delay, receipts and paper fills without authorizing live trading
- EPIC-05: finish Control Center decision UX for 8.0 vs challengers, historical evidence and Prove-or-Break risk

## Governance
Research only. StockLens 8.0 immutable. No automatic promotion. Holdout results are not used to retune closed hypotheses.
