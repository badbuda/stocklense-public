"""Dry-run cockpit must not churn for the same unchanged target within Paper's 50-bp band."""
import csv
import json
from pathlib import Path

import execution_cockpit


def test_no_change_does_not_sell_single_share(tmp_path, monkeypatch):
    plan=tmp_path/"plan.json"
    signal=tmp_path/"signal.json"
    ledger=tmp_path/"ledger.csv"
    out=tmp_path/"out.json"
    plan.write_text(json.dumps({"signal_date":"2026-10-08","target":{"qqq_weight":0.0,"tqqq_weight":0.985,"leverage":3.0}}))
    signal.write_text(json.dumps({"action":"NO_CHANGE","latest":{"features":{"close":747.58},"generated_at_utc":"2026-10-08T22:00:00Z"}}))
    row={"qqq_shares":"0","tqqq_shares":"1197","equity":"97427.96316081587","tqqq_close":"80.22"}
    with ledger.open("w",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
    monkeypatch.setattr(execution_cockpit,"next_xnys_session",lambda _: "2026-10-09")
    monkeypatch.setattr(execution_cockpit,"save",lambda rows:{"status":"NO_ORDERS"})
    result=execution_cockpit.build(str(plan),str(signal),str(ledger),str(out))
    assert result["mode"]=="PAPER"
    assert result["live_submission_authorized"] is False
    assert result["no_change_tolerance_applied"] is True
    assert result["pretrade_target_weight_gap"] <= 0.005
    assert result["orders"]==[]
    assert result["target_positions"]=={"QQQ":0,"TQQQ":1197}
