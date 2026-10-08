from __future__ import annotations
def explain_next_transitions(signal:dict)->dict:
    x=signal["latest"];f=x["features"];level=int(x["level"]);v=float(f["vol20"]);c=float(f["close"]);s=float(f["sma200"])
    if x["defense_active"]: primary="Defense remains until frozen trend/momentum rules release it."
    elif level==3: primary=f"VOL20 needs +{max(0,.32-v)*100:.2f} pp to reach the 32% L3→L2 volatility threshold."
    elif level==2: primary=f"VOL20 is {(v-.28)*100:.2f} pp above L2→L3 and {(.42-v)*100:.2f} pp below L2→L1."
    else: primary=f"VOL20 is {(v-.38)*100:.2f} pp above L1→L2 and {(v-.28)*100:.2f} pp above L1→L3."
    return {"primary":primary,"trend_retention_floor":s*.99,"trend_reentry_threshold":s*1.01,"close":c,"observational_only":True}
