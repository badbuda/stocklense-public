from __future__ import annotations
import json
from stocklens.core import LEVEL_LEVERAGE,TARGET_INVESTED_FRACTION,weights_for_leverage

FROZEN_CONTRACT={
 "levels":{"1":1.25,"2":2.0,"3":3.0},
 "invested_fraction":0.985,
 "trend":{"risk_on_floor":0.99,"risk_off_reentry":1.01},
 "vol":{"l3_to_l2":0.32,"l2_to_l3":0.28,"l2_to_l1":0.42,"l1_to_l3":0.28,"l1_to_l2":0.38},
 "defense":"SMA50<SMA200 AND MOM12<=0",
 "execution":{"reductions":"OPEN+1M","additions":"OPEN+2M","fee_bps":2},
}
def validate_contract():
 errors=[]
 if {str(k):v for k,v in LEVEL_LEVERAGE.items()}!=FROZEN_CONTRACT["levels"]:errors.append("LEVEL_LEVERAGE")
 if TARGET_INVESTED_FRACTION!=0.985:errors.append("INVESTED_FRACTION")
 expected={1.25:(.875,.125),2.0:(.5,.5),3.0:(0,1)}
 for lev,w in expected.items():
  if weights_for_leverage(lev)!=w:errors.append(f"WEIGHTS_{lev}")
 result={"status":"PASS" if not errors else "FAIL","errors":errors,"contract":FROZEN_CONTRACT}
 if errors:raise RuntimeError("FROZEN_CONTRACT_DRIFT:"+",".join(errors))
 return result
if __name__=="__main__":print(json.dumps(validate_contract(),indent=2))
