import json
from backtest_calendar_year_fragility import build
def test_leave_one_year_out_is_deterministic(tmp_path,monkeypatch):
    monkeypatch.setattr("backtest_calendar_year_fragility.identity",lambda *a,**k:{"generation_id":"TEST"})
    rows=[];price=100.0
    for y in (2024,2025):
      for m in range(1,13):
        price*=1.01
        rows.append({"date":f"{y}-{m:02d}-15","close":price,"leverage":1.0})
    w=tmp_path/"w.json";o=tmp_path/"o.json";w.write_text(json.dumps({"replay":{"rows":rows}}))
    x=build(str(w),str(o));assert len(x["calendar_years"])==2;assert len(x["leave_one_year_out"])==2

def test_short_replay_is_not_labeled_long_horizon_robustness(tmp_path,monkeypatch):
    monkeypatch.setattr("backtest_calendar_year_fragility.identity",lambda *a,**k:{"generation_id":"TEST"})
    rows=[];price=100.0
    for i in range(30):
      price*=1.001;rows.append({'date':f'2026-01-{i+1:02d}' if i<28 else f'2026-02-{i-27:02d}','close':price,'leverage':1.0})
    w=tmp_path/'w.json';o=tmp_path/'o.json';w.write_text(json.dumps({'replay':{'rows':rows}}))
    x=build(str(w),str(o));assert x['coverage']['evidence_scope']=='SHORT_REPLAY_ONLY';assert x['coverage']['warning']
