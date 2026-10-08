from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime,timezone

def build(out="research/reports/LATEST.md"):
 s=json.loads(Path("research/AUTONOMY_STATE.json").read_text())
 d=json.loads(Path("research/validation/challenger_dossiers.json").read_text())
 rpath=Path("research/prospective/registry.json");reg=json.loads(rpath.read_text()) if rpath.exists() else {"candidates":[]}
 rmap={x["experiment_id"]:x for x in reg.get("candidates",[])}
 pob=json.loads(Path("docs/prove_or_break.json").read_text()) if Path("docs/prove_or_break.json").exists() else {}
 hist=json.loads(Path("docs/workbench.json").read_text()).get("historical_performance_summary",{}) if Path("docs/workbench.json").exists() else {}
 pub=json.loads(Path("docs/publication_audit.json").read_text()) if Path("docs/publication_audit.json").exists() else {}
 rows=d.get("dossiers",d.get("experiments",[]));by={x["experiment_id"]:x for x in rows}
 lines=["# StockLens Research — Latest Human Report","",f"Generated: {datetime.now(timezone.utc).isoformat()}","","## שורה תחתונה",
 "StockLens 8.0 נשאר קפוא ולא שונה. אין קידום אוטומטי של אף challenger.","",
 "## מצב אימות נוכחי",
 f"- Prove-or-Break: {sum(x.get('status')=='PASS' for x in pob.get('checks',[]) if x.get('id')!='PROSPECTIVE_IMPLEMENTATION')}/{sum(x.get('id')!='PROSPECTIVE_IMPLEMENTATION' for x in pob.get('checks',[]))} retrospective checks PASS; prospective={next((x.get('status') for x in pob.get('checks',[]) if x.get('id')=='PROSPECTIVE_IMPLEMENTATION'),'MISSING')}.",
 f"- Historical LEAN evidence: {hist.get('sessions','?')} sessions; MaxDD {hist.get('max_drawdown_pct','?')}%; NAV multiple {hist.get('last_nav_multiple','?')}.",
 f"- Canonical historical CAGR: {hist.get('cagr_status','BLOCKED')}; אין להסיק CAGR מה-screenshot.",
 f"- Latest publication gate: {pub.get('status','UNKNOWN')}.",""]
 active=s.get("active_experiments",[])
 if active:
  lines+=["## מחקר פעיל"]
  for a in active:
   x=by.get(a["id"],{});p=(x.get("evidence",{}).get("period_result",{}).get("periods",{}));h=p.get("holdout",{});pros=rmap.get(a["id"])
   lines.append(f"- **{a['id']}** — {x.get('disposition',a.get('status'))}.")
   if h: lines.append(f"  Holdout: excess CAGR {h.get('excess_cagr',0):.2%}; MaxDD {h.get('max_drawdown',0):.2%}; improvement vs baseline {h.get('drawdown_delta',0):.2%}.")
   if pros:
    hp=Path("research/prospective")/(a["id"]+".csv");n=max(0,len(hp.read_text().splitlines())-1) if hp.exists() else 0
    lines.append(f"  Prospective tracking inception: {pros['inception_date']}; כרגע {n} sessions עתידיים אמיתיים. רק completed XNYS sessions עם date > inception נספרים; אין backfill של יום ה-inception או קודם ואין pre-close ingest.")
   if x.get("robustness")=="NOT_VALIDATED": lines.append("  חשוב: היעד המוגדר מראש עשוי לעבור, אבל robustness מלא עדיין לא עבר ולכן אין promotion.")
  lines.append("")
 failed=s.get("failed_hypotheses",[])
 if failed:
  lines+=["## ניסויים שנסגרו"]
  for x in failed: lines.append(f"- **{x['id']}** — {x.get('status')}: {x.get('reason','')}")
  lines.append("")
 lines+=["## מה המערכת עושה עכשיו"]
 for x in (s.get("next_work") or s.get("next_actions",[])): lines.append(f"- {x}")
 lines+=["","## Governance","Research only. StockLens 8.0 immutable. No automatic promotion. Holdout results are not used to retune closed hypotheses."]
 p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text("\n".join(lines)+"\n");return str(p)
if __name__=="__main__":print(build())
