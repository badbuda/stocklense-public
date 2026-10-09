from __future__ import annotations
import json
from pathlib import Path

PATH=Path("governance/qc_724_daily_state_manifest.json")
EXPECTED={
 "sessions":3774,
 "first_time_utc":"2009-09-01T20:01:00Z",
 "last_time_utc":"2024-08-29T20:01:00Z",
 "leverage_sha256":"c153c169bb6764274ad5cc5021dfdad36e4e2ead70881ee7e4954a8a83e39ba3",
 "daily_date_leverage_sha256":"caa10bea0a07f3c5f6f60fef49fa407844da4ce514fa552e5202d6d1d10cefb5",
 "daily_session_dates_sha256":"feacf22f410c9f7fcf129b30e91c03c9a924c80e7a2b88dd8839103547adcb08",
 "full_state_sha256":"1c7751a0cd816500ef838ba7532c825cd4764730dda54cfbc5d55ea949c809d5",
 "leverage_counts":{"0.0":274,"1.25":387,"2.0":76,"3.0":3037},
 "daily_transitions":66,
}
def validate_daily_state_manifest():
 d=json.loads(PATH.read_text())
 errors=[k for k,v in EXPECTED.items() if d.get(k)!=v]
 if d.get("python_daily_recomputation_proven") is not False: errors.append("PARITY_SCOPE")
 if errors: raise RuntimeError("QC_DAILY_STATE_MANIFEST_DRIFT:"+",".join(errors))
 return {"status":"PASS","sessions":d["sessions"],"leverage_sha256":d["leverage_sha256"],"scope":d["scope"]}
if __name__=="__main__": print(json.dumps(validate_daily_state_manifest(),indent=2))
