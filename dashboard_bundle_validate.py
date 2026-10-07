from pathlib import Path
import json

def validate(path="docs/index.html"):
 validate_simulator_artifact()
 h=Path(path).read_text()
 checks={
  "single_script": h.count("<script>")==1 and h.count("</script>")==1,
  "single_document": h.count("</html>")==1 and h.rstrip().endswith("</script></body></html>"),
  "primary_sections": all(f'id="{x}"' in h for x in ("overview","performance","research","activity")),
  "core_feeds": all(x in h for x in ("data.json","research_snapshot.json","activity.json")),
  "localized_failure_state": all(x in h for x in ("feedError","UNKNOWN","נסה שוב")),
  "independent_core_feeds": "Promise.all([getJSON(\'data.json\')" not in h and all(f"getJSON(\'{x}\').then" in h for x in ("data.json","research_snapshot.json","activity.json")),
  "legacy_preserved": Path("docs/legacy.html").exists(),
  "research_curves_valid": validate_research_curves(),
  "session_freshness_ui": all(x in h for x in ("market_session_freshness","latest_completed_xnys_session","latest_completed_close_utc","sessions_behind_latest_completed")),
  "publication_freshness_ui": all(x in h for x in ("generated_at_utc","max_age_minutes","Publication ")),
  "daily_brief_ui": all(x in h for x in ("daily_brief.json","dailyBrief","Daily Brief")),
  "workbench_simulator_contract": validate_workbench_simulator(),
 }
 failed=[k for k,v in checks.items() if not v]
 if failed: raise SystemExit("DASHBOARD_BUNDLE_INVALID: "+",".join(failed))
 print("DASHBOARD_BUNDLE_OK")
 return checks

def validate_simulator_artifact(path="docs/simulator_smoke.json"):
 p=Path(path)
 try: d=json.loads(p.read_text())
 except Exception: raise SystemExit("SIMULATOR_SMOKE_INVALID_OR_MISSING")
 if d.get("accounting_invariants",{}).get("status")!="PASS": raise SystemExit("SIMULATOR_ACCOUNTING_NOT_PASS")
 if d.get("full_lean_execution_parity") is not False: raise SystemExit("SIMULATOR_PARITY_CLAIM_INVALID")
 if not d.get("replay_dataset_sha256") or not d.get("contract_sha256"): raise SystemExit("SIMULATOR_PROVENANCE_MISSING")
 return d

def validate_workbench_simulator(path="docs/workbench.html"):
 try: h=Path(path).read_text()
 except Exception:return False
 required=("REPLAY APPROXIMATION","Decision Timeline","Session Drill-down","Session Navigator","Scenario A/B Compare","Capital Flow Explorer","Period Breakdown","Drawdown Episodes","Exposure Attribution","stocklens-decision-timeline.csv","SIMULATED_REPLAY_COST_NOT_LEAN_FILL","estimated_transaction_cost","stocklens-scenarios","SIMULATOR_ACCOUNTING_INVARIANT_FAILED","accounting_invariants","drillGrossPL","drillCost","accountingStatus","accountingNavDelta","markSelectedSession","הפקדה חודשית","Replay Transaction Costs","costTurnover","costPaidPct","cumulative_cost","Transaction Cost Sensitivity","costSensitivityRows","No model selection or promotion","Capital Path Ledger","capitalLedgerFilter","row_reconciliation_failures","nav_before_cost","DATA.simulator_contract","cost_sensitivity_bps")
 forbidden=("stocklens_scenarios",)
 return all(x in h for x in required) and all(x not in h for x in forbidden)

def validate_research_curves(path="docs/research_curves.json"):
 p=Path(path)
 try: x=json.loads(p.read_text())
 except Exception:return False
 s=x.get("series",{})
 return bool(s.get("QQQ")) and bool(s.get("SL8_RESEARCH_APPROX")) and x.get("evidence_scope")=="RESEARCH_APPROXIMATION_NOT_QC_PARITY"
if __name__=="__main__": validate()
