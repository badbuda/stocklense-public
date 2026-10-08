from pathlib import Path
import json,re

DOCS=Path("docs")

def main():
    failures=[]
    index=(DOCS/"index.html").read_text(encoding="utf-8")
    execution=(DOCS/"execution.html").read_text(encoding="utf-8")
    if "querySelectorAll('nav button[data-page]')" not in index:
        failures.append("mission_control_nav_scope")
    for page in (index,execution):
        for href in re.findall(r'href=["\\\']([^"\\\']+)',page):
            if href.startswith("./"):
                target=DOCS/href[2:].split("#",1)[0].split("?",1)[0]
                if not target.exists(): failures.append("broken_link:"+href)
    feeds=set(re.findall(r"""getJSON\(['"]([^'"]+)""",index))
    feeds.update(re.findall(r"""fetch\(['"]([^'"]+)""",index))
    for feed in feeds:
        feed=feed.split("?",1)[0]
        if feed and not (DOCS/feed).exists(): failures.append("missing_feed:"+feed)
    data=json.loads((DOCS/"data.json").read_text())
    for key in ("signal","paper","execution_plan","execution_readiness","automation_guard","execution_cockpit","execution_policy"):
        if key not in data: failures.append("missing_data_contract:"+key)
    cockpit=data.get("execution_cockpit",{})
    for key in ("current_positions","target_positions","orders","reconciliation","execution_window"):
        if key not in cockpit: failures.append("missing_execution_cockpit:"+key)
    policy=data.get("execution_policy",{})
    if policy.get("automatic_catchup") is not False: failures.append("execution_policy_auto_catchup_not_disabled")
    if policy.get("live_submission_authorized") is not False: failures.append("execution_policy_live_not_fail_closed")
    if cockpit.get("live_submission_authorized") is not False:
        failures.append("cockpit_live_not_fail_closed")
    for token in ("Current → Target → Dry-run orders",'id="positions"','id="orders"','id="window"','id="retry"','id="timingPolicy"','id="nextSafe"'):
        if token not in execution: failures.append("execution_ui_missing:"+token)
    if data.get("automation_guard",{}).get("live_trading_enabled") is not False:
        failures.append("live_trading_not_fail_closed")
    if failures:
        raise SystemExit("USER_JOURNEY_INVALID: "+",".join(sorted(set(failures))))
    print("USER_JOURNEY_PASS: primary navigation, local routes, feeds, execution data and live safety boundary")

if __name__=="__main__":
    main()
