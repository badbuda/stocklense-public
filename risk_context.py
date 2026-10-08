from __future__ import annotations
def build_risk_context(signal:dict)->dict:
    x=signal["latest"];f=x["features"];v=float(f["vol20"]);close=float(f["close"]);s200=float(f["sma200"]);s50=float(f["sma50"]);mom=float(f["mom12"])
    level=int(x["level"])
    thresholds={"l3_drop_vol":0.32,"l2_recover_vol":0.28,"l2_drop_vol":0.42,"l1_recover_l2_vol":0.38,"trend_retention_ratio":0.99,"trend_reentry_ratio":1.01}
    distances={
      "vol_to_32":0.32-v,"vol_to_28":v-0.28,"vol_to_42":0.42-v,"vol_to_38":v-0.38,
      "close_vs_retention_floor_pct":close/(s200*0.99)-1 if s200 else None,
      "close_vs_reentry_threshold_pct":close/(s200*1.01)-1 if s200 else None,
      "sma50_vs_sma200_pct":s50/s200-1 if s200 else None,"mom12":mom}
    flags=[]
    if level==3 and 0<=0.32-v<=0.03: flags.append("NEAR_L3_VOL_DOWNSHIFT")
    if close>=s200*0.99 and close<=s200*1.02: flags.append("NEAR_LONG_TREND_BOUNDARY")
    if s50<s200: flags.append("SMA50_BELOW_SMA200")
    if mom<=0: flags.append("MOM12_NONPOSITIVE")
    return {"thresholds":thresholds,"distances":distances,"flags":flags,"observational_only":True}
