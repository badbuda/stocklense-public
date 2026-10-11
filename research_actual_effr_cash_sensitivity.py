"""Reference EFFR effective-date sensitivity, never historical broker cash alpha.

No historical vendor first-seen invented: effective dates ONLY; assumed two-
completed-NYSE-session availability *stress*, not timestamp attestation. Input
is a previously downloaded official NY Fed API snapshot; not revised-vintage
or taxable net broker yield. No online access, orders, or model promotion.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import hashlib
import json
import math

from observed_etf_two_question_audit import load, _metrics, SPLITS, START_CAPITAL
from observed_etf_four_challengers_batch import simulate as frozen_reference
from research_cash_rate_broker_proxy import simulate as credit_simulate

SOURCE = Path("research/private/effr_effective_dates_without_publication_clock.json")
OUT = Path("research/results/effr_effective_date_cash_sensitivity.json")
REPORT = Path("research/reports/effr_effective_date_cash_sensitivity.md")
SOURCE_URL_PREFIX = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
PERMITTED_HAIRCUTS = (0.0, 0.01, 0.02)
ASSUMED_COMPLETED_SESSIONS_DELAY = 2
MAX_STALENESS_CALENDAR_DAYS = 8


def normalize(source):
    if not isinstance(source, dict) or source.get("schema_version") != 1 or source.get("series") != "EFFR":
        raise ValueError("EFFR_SOURCE_CONTRACT_FAILED")
    url = source.get("source_url")
    if not isinstance(url, str) or not url.startswith(SOURCE_URL_PREFIX + "?"):
        raise ValueError("EFFR_OFFICIAL_PROVIDER_URL_REQUIRED")
    if (source.get("not_broker_deposit_yield") is not True
            or source.get("publication_clock_available_in_api") is not False
            or source.get("asof_tradability_verified") is not False):
        raise ValueError("EFFR_CANNOT_SELF_ASSERT_PIT_OR_BROKER_YIELD")
    observations = source.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("EFFR_OBSERVATIONS_MISSING")
    out = []
    for obj in observations:
        if not isinstance(obj, dict) or obj.get("provider_publication_timestamp_verified") is not False:
            raise ValueError("EFFR_NOT_INDEPENDENT_PUBLICATION_PROOF")
        try:
            eff = date.fromisoformat(obj["effective_date"])
            pct = obj["rate_percent"]
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("EFFR_INVALID_ROW") from exc
        if type(pct) not in (int, float) or not math.isfinite(pct) or not 0 <= pct <= 25:
            raise ValueError("EFFR_PERCENT_UNITS_INVALID")
        out.append((eff, float(pct)/100.0))
    if out != sorted(set(out)) or len(set(x[0] for x in out))!=len(out):
        raise ValueError("EFFR_DUPLICATE_OR_UNSORTED_EFFECTIVE_DATES")
    return out


def rate_schedule(dates, source):
    """Conservatively select rates dated <= 2 completed market sessions ago.

    This is an explicit hypothetical clock delay, NOT historical proof of
    when the NY Fed API was available. First two days earn zero by convention
    due to missing pre-cohort warmup data and are counted as such.
    """
    raw = normalize(source)
    if not isinstance(dates, list) or len(dates) < 3:
        raise ValueError("EFFR_PRICE_COHORT_TOO_SHORT")
    ds = [date.fromisoformat(x) for x in dates]
    if ds != sorted(set(ds)):
        raise ValueError("EFFR_INVALID_MARKET_CALENDAR")
    result = [0.0, 0.0]
    rate_used = []
    pointer = -1
    for i in range(2,len(ds)):
        cutoff = ds[i-ASSUMED_COMPLETED_SESSIONS_DELAY]
        while pointer+1<len(raw) and raw[pointer+1][0] <= cutoff:
            pointer+=1
        if pointer<0:
            raise ValueError("EFFR_NO_PRIOR_EFFECTIVE_DATE_AVAILABLE")
        eff, rate = raw[pointer]
        if (ds[i-1]-eff).days > MAX_STALENESS_CALENDAR_DAYS:
            raise ValueError("EFFR_SOURCE_STALE_OR_MISSING_DATES")
        result.append(rate)
        rate_used.append({"modeled_open":dates[i],"selected_effective_date":eff.isoformat()})
    assert len(result)==len(ds)
    return result, rate_used


def era(path, days, start, end):
    # The cash ledger owns NAVs; exchange dates are carried by the market source.
    if len(path["navs"]) != len(days) or days != sorted(set(days)):
        raise ValueError("EFFR_MARKET_DATES_AND_LEDGER_MISMATCH")
    a=[i for i,d in enumerate(days) if start<=d<=end]
    if not a:
        raise ValueError("EFFR_MISSING_ERA")
    first,last=a[0],a[-1]
    prev=START_CAPITAL if first==0 else path["navs"][first-1]
    return _metrics(path["navs"][first:last+1],days[first:last+1],first=prev)


def evaluate(market, source):
    rows=market["daily"]
    if market.get("snapshot_sha256") != "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129":
        raise ValueError("EFFR_BASELINE_PRICE_SOURCE_CHANGED")
    days = [r["date"] for r in rows]
    schedule, joins = rate_schedule(days,source)
    baseline = credit_simulate(rows,[0.0]*len(rows))
    ref = frozen_reference(rows,mode="frozen",lag=0,slippage_bps=10.,annual_cash_yield=0.)
    if any(abs(a-b)>1e-5 for a,b in zip(baseline["navs"],ref["navs"])):
        raise ValueError("EFFR_ZERO_INTEREST_FROZEN_NAV_PARITY_FAILED")
    results={}
    for haircut in PERMITTED_HAIRCUTS:
        conditional = [0.0 if i < ASSUMED_COMPLETED_SESSIONS_DELAY else max(0.0,rate-haircut)
                       for i,rate in enumerate(schedule)]
        test=credit_simulate(rows,conditional)
        stats=test["stats"]
        results[f"{int(haircut*10000)}_bps_haircut"]={
            "assumed_broker_rate_haircut_bps":int(haircut*10000),
            "cagr":stats["cagr"],"max_drawdown":stats["max_drawdown"],
            "cagr_delta_pp":100*(stats["cagr"]-baseline["stats"]["cagr"]),
            "modeled_gross_interest_dollars":test["cash_interest_dollars"],
            "eras":{k:{
                "cagr_delta_pp":100*(era(test,days,a,b)["cagr"]-era(baseline,days,a,b)["cagr"]),
                "maxdd_delta_pp":100*(era(test,days,a,b)["max_drawdown"]-era(baseline,days,a,b)["max_drawdown"])
            } for k,(a,b) in SPLITS.items()},
            "broker_credit_observed":False,
        }
    fingerprint=hashlib.sha256(json.dumps(source,sort_keys=True,
                        separators=(",",":")).encode()).hexdigest()
    return {
        "schema_version":1,
        "kind":"EFFR_EFFECTIVE_DATE_CONDITIONAL_CASH_ACCOUNTING_NOT_BROKER_YIELD",
        "baseline":baseline["stats"],
        "sample_sessions":len(rows),"effr_observations":len(normalize(source)),
        "source_snapshot_sha256":fingerprint,
        "cohort_start":rows[0]["date"],"cohort_end":rows[-1]["date"],
        "hypothetical_completed_session_publication_delay":ASSUMED_COMPLETED_SESSIONS_DELAY,
        "initial_zero_yield_warmup_sessions":ASSUMED_COMPLETED_SESSIONS_DELAY,
        "first_effective_rate_used":joins[0]["selected_effective_date"],
        "last_effective_rate_used":joins[-1]["selected_effective_date"],
        "independently_verified_historical_publication_times":False,
        "independently_verified_historical_revisions":False,
        "interest_paid_by_real_broker_proven":False,
        "net_after_tax_fx_costs":False,
        "frozen_daily_nav_parity":True,
        "assumed_rate_scenarios":results,
        "historical_reused_sample_no_pristine_oos":True,
        "baseline_frozen_stocklens8_changed":False,
        "synthetic_tqqq_used":False,
        "capital_deployment_authorized":False,
        "automatic_promotion":False,
    }


def build():
    if not SOURCE.exists():
        raise ValueError("EFFR_ORIGINAL_SOURCE_ARTIFACT_REQUIRED")
    r=evaluate(load(),json.loads(SOURCE.read_text(encoding="utf-8")))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    lines=["# Historical EFFR effective-date CASH accounting sensitivity","",
       "**Conditional and retrospective, not actual cash sweep yield.**",
       "No historical provider first-seen was verified; using an assumed",
       "two *completed exchange sessions* delay, not a claim about any Fed",
       "publication clock. First two observations yield zero by convention.",
       "No actual Excellence Trade cash terms, FX fees or taxes proved.",
       "","| Assumed cash credit | CAGR | Delta CAGR pp | MaxDD | Gross conditional interest |",
       "|---|---:|---:|---:|---:|"]
    b=r["baseline"]
    lines.append(f'| Zero credit frozen | {b["cagr"]:.3%} | 0 | {b["max_drawdown"]:.3%} | 0 |')
    for k,v in r["assumed_rate_scenarios"].items():
        lines.append(f'| EFFR minus {v["assumed_broker_rate_haircut_bps"]}bps, floored 0 | {v["cagr"]:.3%} | {v["cagr_delta_pp"]:+.3f} | {v["max_drawdown"]:.3%} | {v["modeled_gross_interest_dollars"]:.2f} |')
    lines.extend(["","The rates are real effective-date observations, but time-of-publication",
                  "and deposit entitlement are **assumptions, not authenticated evidence**.",
                  "This is not an investable alpha strategy or change to StockLens 8.0."])
    REPORT.write_text("\n".join(lines)+"\n")
    print("STOCKLENS_EFFR_CASH_CONDITIONAL="+json.dumps({
        "baseline_cagr":b["cagr"],"baseline_maxdd":b["max_drawdown"],
        "rate_observations":r["effr_observations"],
        "scenario_cagr":{k:v["cagr"] for k,v in r["assumed_rate_scenarios"].items()},
        "scenario_delta_pp":{k:v["cagr_delta_pp"] for k,v in r["assumed_rate_scenarios"].items()},
        "clock_proven":False,"broker_yield_proven":False,"promotion":False
    },sort_keys=True))
    return r


if __name__=="__main__":
    build()
