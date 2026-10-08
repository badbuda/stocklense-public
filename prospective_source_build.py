from __future__ import annotations
import json
from research_data_adapter import build_baseline_dataset
from research_upshift_confirmation import build as build_upshift

BASELINE="research/data/stocklens8_daily.csv"
OUT="research/data/SL9-007-UPSHIFT-CONFIRMATION.csv"

def build():
    baseline=build_baseline_dataset(out=BASELINE)
    challenger=build_upshift(BASELINE,OUT,up_confirm=2)
    return {
        "kind":"SL9_007_PROSPECTIVE_SOURCE_REBUILD",
        "baseline":baseline,
        "challenger":challenger,
        "output":OUT,
        "queue_mutated":False,
    }

if __name__=="__main__":
    print(json.dumps(build(),indent=2))
