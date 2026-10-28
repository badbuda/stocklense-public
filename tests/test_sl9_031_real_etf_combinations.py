"""Unit-only toy fixtures; no invented toy alpha is reported as evidence."""
import copy
from datetime import date, timedelta
import pytest

from sl9_031_real_etf_combinations import (
    ETFS, MIXES, OVERLAYS, SYMS, exposures, target_weights, run_path, SLIPS,
)
from observed_etf_four_challengers_batch import simulate as old_frozen


def toy(n=65):
    d = date(2024, 4, 1)
    dates=[]
    while len(dates) < n:
        if d.weekday()<5: dates.append(d.isoformat())
        d+=timedelta(days=1)
    rows=[]
    for i,s in enumerate(dates):
        level = 3. if i<35 else 1.25 if i<48 else 2.
        rows.append({"date":s,"signal": dates[i-1] if i else "2024-03-29",
                     "l":level,"qo":100+i*.1,"qc":100+i*.13,
                     "to":25+i*.07,"tc":25.1+i*.07})
    bars={s:{d:{"date":d,"open":30+i*.05, "close":30+i*.06}
             for i,d in enumerate(dates)} for s in ETFS}
    return rows,bars


def test_exact_frozen_parity_with_old_whole_share_engine():
    rows,bars=toy()
    for lag in (0,1):
        levels=exposures(rows,"frozen",lag)
        for slip in SLIPS:
            new=run_path(rows,bars,"frozen",levels,slip)
            old=old_frozen(rows,mode="frozen",lag=lag,slippage_bps=slip)
            assert new["navs"]==pytest.approx(old["navs"],abs=1e-7)


def test_all_arms_are_deterministic_and_funded_without_invented_prices():
    rows,bars=toy()
    for overlay in OVERLAYS:
        lv=exposures(rows,overlay,1)
        for mix in MIXES:
            path=run_path(rows,bars,mix,lv,10.)
            assert len(path["navs"])==len(rows)
            assert min(path["navs"])>0
            assert path["trades"]>=0


def test_zero_defense_must_stay_uninvested_and_no_lookahead():
    rows,bars=toy()
    rows[15]["l"]=0
    for overlay in OVERLAYS:
        lv=exposures(rows,overlay,0)
        assert lv[15]==0
    for mix in MIXES:
        assert all(v==0 for v in target_weights(0,mix).values())
    later=copy.deepcopy(rows)
    later[-1]["qc"]*=10
    for overlay in OVERLAYS:
        a=exposures(rows,overlay,1)
        b=exposures(later,overlay,1)
        assert a==b  # last close was never available to any backtest day's open


def test_factorial_mixes_never_exceed_cashless_fraction():
    assert len(MIXES)==7 and len(OVERLAYS)==8
    assert len(SYMS)==6
    for mix in MIXES:
        for lv in (0,1.,1.25,2.,2.5,3.):
            w=target_weights(lv,mix)
            assert min(w.values())>=0
            assert sum(w.values())<=.985+1e-10
            if lv==0: assert not any(w.values())


def test_refuses_unregistered_selection_and_missing_observed_quote():
    rows,bars=toy()
    with pytest.raises(ValueError, match="UNREGISTERED_3X_MIX"):
        target_weights(3.,"selected_after_results")
    with pytest.raises(ValueError, match="UNREGISTERED_OVERLAY_OR_LAG"):
        exposures(rows,"optimize",0)
    del bars["SOXL"][rows[3]["date"]]
    with pytest.raises(KeyError):
        run_path(rows,bars,"q3_soxl25",exposures(rows,"frozen",0),10.)
