from __future__ import annotations
import csv,json
from datetime import datetime,timezone
from pathlib import Path
from json_artifacts import write_json_atomic
from simulator_contract import as_dict as simulator_contract

def _f(v):
 try:return float(v)
 except:return None

def _j(path,default=None):
 try:return json.loads(Path(path).read_text())
 except (FileNotFoundError,json.JSONDecodeError,OSError):return {} if default is None else default

def build(out="docs/workbench.json"):
 rows=list(csv.DictReader(Path("historical_replay/daily_states.csv").open()))
 replay=[]
 prev=None
 for r in rows:
  lev=_f(r["target_leverage"])
  event=None
  if prev is not None and lev!=prev:event="BUY_EXPOSURE" if lev>prev else "SELL_EXPOSURE"
  replay.append({"date":r["asof_date"],"level":int(r["level"]),"leverage":lev,"close":_f(r["close"]),"sma50":_f(r["sma50"]),"sma200":_f(r["sma200"]),"vol20":_f(r["vol20"]),"mom12":_f(r["mom12"]),"action":r["action"],"event":event})
  prev=lev
 gm=json.loads(Path("governance/qc_724_leverage_transitions.json").read_text())
 transitions=[{"date":x[0],"leverage":x[1],"from_leverage":(gm["transitions"][i-1][1] if i else None),"direction":("INITIAL" if i==0 else ("UP" if x[1]>gm["transitions"][i-1][1] else "DOWN")),"days_since_previous":((datetime.fromisoformat(x[0])-datetime.fromisoformat(gm["transitions"][i-1][0])).days if i else None)} for i,x in enumerate(gm["transitions"])]
 durations=[x["days_since_previous"] for x in transitions[1:] if x["days_since_previous"] is not None]
 data=json.loads(Path("docs/data.json").read_text())
 daily_manifest=json.loads(Path("governance/qc_724_daily_state_manifest.json").read_text())
 from lean_regime_analytics import build as build_regimes
 regime_analytics=build_regimes()
 try:
  full_export=json.loads(Path("shadow_history/qc_full_run_export.json").read_text())
 except Exception:
  from qc_full_run_export import validate
  full_export=validate()
 gold=json.loads(Path("research/golden_evidence/qc_68920881.json").read_text())
 sig=data.get("signal",{})
 robustness_summary={}
 try:
  pob=_j("docs/prove_or_break.json",{});adv=_j("docs/backtest_adversarial.json",{});conc=_j("docs/backtest_return_concentration.json",{});abl=_j("docs/backtest_topday_ablation.json",{});rec=_j("docs/backtest_recovery.json",{});frag=_j("docs/backtest_path_fragility.json",{})
  checks=pob.get("checks") or []
  cases={x.get("removed_top_positive_sessions"):x for x in (abl.get("cases") or []) if isinstance(x,dict)}
  costs={x.get("id"):x for x in ((adv.get("stresses") or adv.get("scenarios") or [])) if isinstance(x,dict) and str(x.get("id","")).startswith("COST_")}
  deepest=rec.get("deepest_episode") or {};longest=rec.get("longest_episode") or {};windows=frag.get("rolling_windows") or []
  robustness_summary={"status":pob.get("status") or "PENDING_CANONICAL_OUTPUTS","retrospective_passed":sum(x.get("status")=="PASS" for x in checks if x.get("id")!="PROSPECTIVE_IMPLEMENTATION"),"retrospective_total":sum(x.get("id")!="PROSPECTIVE_IMPLEMENTATION" for x in checks),"prospective_status":next((x.get("status") for x in checks if x.get("id")=="PROSPECTIVE_IMPLEMENTATION"),"MISSING"),"baseline_replay_cagr":(adv.get("baseline") or {}).get("cagr"),"baseline_replay_max_drawdown":(adv.get("baseline") or {}).get("max_drawdown"),"cost_200bps_cagr":(costs.get("COST_200BPS") or {}).get("cagr"),"top5_removed_return":(cases.get(5) or {}).get("remaining_compounded_gross_return"),"top10_positive_return_share":conc.get("top10_positive_gross_return_share"),"deepest_drawdown":deepest.get("max_drawdown"),"deepest_recovered":bool(deepest.get("recovery_date")) if deepest else None,"longest_underwater_sessions":longest.get("underwater_sessions"),"worst_21d_return":next((x.get("worst_return_window",{}).get("compounded_gross_return") for x in windows if x.get("sessions")==21),None),"evidence_scope":"ONE_YEAR_REPLAY_APPROXIMATION","automatic_promotion":False,"interpretation":"Retrospective survival evidence only. PASS is not proof of future return; prospective evidence remains required."}
 except Exception as exc:
  robustness_summary={"status":"UNAVAILABLE","error":type(exc).__name__,"error_detail":str(exc)[:160],"retrospective_passed":0,"retrospective_total":0,"prospective_status":"MISSING","automatic_promotion":False}
 lean_acquisition={}
 try:
  from qc_full_run_acquisition import build as _lean_acquisition
  from qc_full_run_export import validate as _lean_validate, performance_metrics as _lean_perf
  lean_acquisition=_lean_acquisition()
  lean_acquisition["validation"]=_lean_validate()
  lean_acquisition["performance_verification"]=_lean_perf()
  lean_acquisition["project_blocker"]=lean_acquisition.get("status")!="ACQUIRED"
 except Exception as exc:
  lean_acquisition={"status":"UNAVAILABLE","error":type(exc).__name__,"project_blocker":True}
 yahoo_long_history=_j("research/yahoo_long_history.json",{})
 yahoo_reconstruction_summary={
  "status":yahoo_long_history.get("status","PENDING"),
  "evidence_class":yahoo_long_history.get("kind","YAHOO_INDEPENDENT_LONG_HISTORY_RECONSTRUCTION"),
  "execution_parity":False,
  "claim_boundary":yahoo_long_history.get("claim_boundary","Independent Yahoo reconstruction; not original LEAN execution evidence."),
  "sessions":yahoo_long_history.get("sessions"),"start":yahoo_long_history.get("start"),"end":yahoo_long_history.get("end"),
  "strategy_no_contributions":yahoo_long_history.get("strategy_no_contributions",{}),
  "qqq_buy_hold_no_contributions":yahoo_long_history.get("qqq_buy_hold_no_contributions",{}),
  "strategy_with_monthly_3500":yahoo_long_history.get("strategy_with_monthly_3500",{}),
  "qqq_with_monthly_3500":yahoo_long_history.get("qqq_with_monthly_3500",{}),
  "contribution_comparison":yahoo_long_history.get("contribution_comparison",{}),
  "comparison":yahoo_long_history.get("comparison",{}),
  "annual_summary":yahoo_long_history.get("annual_summary",{}),
  "rolling_windows":yahoo_long_history.get("rolling_windows",{}),
  "cost_stress":yahoo_long_history.get("cost_stress",[]),
  "exposure_mix":yahoo_long_history.get("exposure_mix",{}),
  "drawdown_profile":yahoo_long_history.get("drawdown_profile",{}),
  "retroactive_extension":yahoo_long_history.get("retroactive_extension",{}),
  "retroactive_subperiods":yahoo_long_history.get("retroactive_subperiods",[]),
  "research_verdict":yahoo_long_history.get("research_verdict",{}),
  "instrument_semantics":yahoo_long_history.get("instrument_semantics",{})
 }
 research_digest={}
 try:
  from daily_digest import _research_snapshot
  research_digest=_research_snapshot()
 except Exception as exc:
  research_digest={"status":"UNAVAILABLE","error":type(exc).__name__,"experiments":[],"policy":"DESCRIPTIVE_RESEARCH_ONLY_NO_AUTOMATIC_PROMOTION"}
 result={"schema_version":1,"model":"StockLens 8.0 FROZEN","generated_at_utc":datetime.now(timezone.utc).isoformat(),"publication":{"generated_at_utc":datetime.now(timezone.utc).isoformat(),"freshness_semantics":"PUBLICATION_AGE_ONLY_NOT_MARKET_DATA_AGE","signal_asof":sig.get("asof_date"),"market_session_semantics":"SESSION_IDENTITY_ONLY_NOT_WALL_CLOCK_AGE","source":"dashboard_workbench.py"},
  "live":{"asof_date":sig.get("asof_date"),"action":sig.get("action"),"level":sig.get("level"),"target_leverage":sig.get("target_leverage"),"features":sig.get("features",{}),"health":data.get("readiness",{}).get("health_status"),"strong_live_claims_allowed":data.get("evidence_maturity",{}).get("strong_live_claims_allowed",False)},
  "simulator_contract":simulator_contract(),
  "replay":{"evidence":"FROZEN_MODEL_HISTORICAL_REPLAY","start":replay[0]["date"] if replay else None,"end":replay[-1]["date"] if replay else None,"sessions":len(replay),"dataset_sha256":daily_manifest.get("source_dataset_sha256") or "db0889da31af43b1b75e005c1f4ab2cad421dfb55a6c55a77a223e0623950d95","rows":replay,
   "simulation_note":"Capital path is an exposure replay approximation using daily QQQ adjusted-close returns multiplied by prior-session target leverage. It is not TQQQ/QLD execution parity and excludes financing, slippage, fees and leveraged-ETF path effects.","timeline":[{"date":x["date"],"close":x["close"],"level":x["level"],"target_leverage":x["leverage"],"previous_target_leverage":(replay[i-1]["leverage"] if i else None),"leverage_delta":(x["leverage"]-replay[i-1]["leverage"] if i else None),"action":x["action"],"decision_event":x["event"],"is_transition":bool(x["event"]),"event_type":("EXPOSURE_CHANGE" if x["event"] else "SESSION_DECISION"),"evidence":"REPLAY_APPROXIMATION"} for i,x in enumerate(replay)],
   "event_ledger":[{"date":x["date"],"event_type":"EXPOSURE_CHANGE","decision_event":x["event"],"previous_target_leverage":replay[i-1]["leverage"],"target_leverage":x["leverage"],"leverage_delta":x["leverage"]-replay[i-1]["leverage"],"level":x["level"],"close":x["close"],"action":x["action"],"evidence":"REPLAY_APPROXIMATION","execution_parity":False} for i,x in enumerate(replay) if i and x["event"]]},
  "lean_regimes":{"evidence":"QC_7_24_LEVERAGE_TRANSITIONS_GOLDEN_MASTER","start":gm["transitions"][0][0],"end":gm["transitions"][-1][0],"transition_count":gm["transition_count"],"sha256":gm["transition_sha256"],"transitions":transitions,"analytics":{"upshifts":sum(1 for x in transitions if x["direction"]=="UP"),"downshifts":sum(1 for x in transitions if x["direction"]=="DOWN"),"median_days_between_transitions":sorted(durations)[len(durations)//2],"max_days_between_transitions":max(durations)}},
  "evidence_ladder":[{"name":"LEAN regime transitions","status":"VERIFIED_GOLDEN_MASTER","scope":"67 transitions / 2009-2024"},{"name":"Frozen-model daily replay","status":"REPLAY_AVAILABLE","scope":str(len(replay))+" sessions"},{"name":"Prospective live performance","status":"IMMATURE","scope":"Strong live claims disabled"},{"name":"Full LEAN daily equity","status":"MISSING","scope":"Required for execution-parity equity curve"},{"name":"QC screenshot runtime evidence","status":gold["verification_status"],"scope":"Ending equity $"+format(gold["runtime_statistics"]["equity_usd"],",.2f")+"; dates/version/cashflows not established"}],
  "regime_analytics":regime_analytics,
  "research_comparison":research_digest,"yahoo_long_history":yahoo_reconstruction_summary,"yahoo_end_of_day_scorecard":_j("research/yahoo_end_of_day_scorecard.json",{}),"lean_evidence_acquisition":lean_acquisition,
  "robustness_summary":robustness_summary,
  "historical_performance_summary":{"evidence_class":"REAL_LEAN_DAILY_STATE_FINGERPRINT","period_start":daily_manifest["first_time_utc"],"period_end":daily_manifest["last_time_utc"],"sessions":daily_manifest["sessions"],"max_drawdown_pct":daily_manifest["max_drawdown_pct"],"last_nav_multiple":daily_manifest["last_nav_multiple"],"cagr":None,"cagr_status":"BLOCKED_PENDING_FULL_LEAN_EXPORT","cagr_unlock_contract":{"daily_rows_required":3774,"orders_required":345,"required_daily_fields":["date","close","sma50","sma200","vol20","mom12","level","defense","leverage","equity","cash","holdings_value"],"cashflow_semantics_required":True,"raw_same_run_required":True,"synthetic_reconstruction_forbidden":True},"screenshot_equity_usd":gold["runtime_statistics"]["equity_usd"],"screenshot_return_percent":gold["runtime_statistics"]["return_percent"],"screenshot_status":gold["verification_status"],"screenshot_do_not_infer":gold["do_not_infer"],"full_python_input_parity_proven":daily_manifest["python_daily_recomputation_proven"]},
  "lean_daily_manifest":{"sessions":daily_manifest["sessions"],"first_time_utc":daily_manifest["first_time_utc"],"last_time_utc":daily_manifest["last_time_utc"],"leverage_sha256":daily_manifest["leverage_sha256"],"full_state_sha256":daily_manifest["full_state_sha256"],"leverage_counts":daily_manifest["leverage_counts"],"daily_transitions":daily_manifest["daily_transitions"],"max_drawdown_pct":daily_manifest["max_drawdown_pct"],"last_nav_multiple":daily_manifest["last_nav_multiple"],"scope":daily_manifest["scope"],"raw_rows_available":False},
  "full_lean_export":full_export,
  "constraints":{"full_lean_daily_equity_available":full_export.get("execution_parity_ready",False),"full_lean_trade_details_available":full_export.get("execution_parity_ready",False),"interactive_replay_available":True}}
 write_json_atomic(out,result);return result
if __name__=="__main__":print(json.dumps({"sessions":build()["replay"]["sessions"]},indent=2))
