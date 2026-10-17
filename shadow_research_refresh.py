"""Bounded real-provider retry when observed ETF research lags the frozen Shadow.

Never edit raw prices, the 8.0 decision engine, or frozen parity tolerances.
Requires exact agreement across the whole parity gate before publication.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from frozen_decision_parity_gate import compare

RESEARCH_PATH = Path("research/tradable_tqqq_execution_comparison.json")
SIGNAL_PATH = Path("output/latest_signal.json")
# Provider may publish observed TQQQ OHLC after it publishes the daily QQQ close.
RETRYABLE = frozenset(("SIGNAL_DATE_MISMATCH", "QQQ_ADJUSTED_CLOSE_DRIFT"))
MAX_REBUILDS = 3
WAIT_SECONDS = 90


def reconcile(load_report, signal: dict, rebuild, wait,
              *, max_rebuilds: int = MAX_REBUILDS) -> dict:
    """Fail closed: only lag/drift may trigger bounded refetch of genuine prices."""
    if not isinstance(max_rebuilds, int) or max_rebuilds < 0 or max_rebuilds > 5:
        raise ValueError("INVALID_BOUNDED_REFRESH_LIMIT")
    for attempt in range(max_rebuilds + 1):
        verdict = compare(load_report(), signal)
        if verdict["status"] == "PASS":
            print("REAL_OBSERVED_ETF_FROZEN_PARITY_PASS:attempt=" + str(attempt))
            return verdict
        errors = set(verdict["errors"])
        if not errors or not errors.issubset(RETRYABLE):
            raise RuntimeError("NON_RETRYABLE_FROZEN_RESEARCH_PARITY:" +
                               ",".join(verdict["errors"]))
        print("PROVIDER_RESEARCH_NOT_ALIGNED:attempt=" + str(attempt) +
              ":signal=" + str(verdict["signal_asof"]) +
              ":research=" + str(verdict["research_asof"]) +
              ":errors=" + ",".join(verdict["errors"]), flush=True)
        if attempt == max_rebuilds:
            break
        if attempt:
            wait(WAIT_SECONDS)
        # Re-run the ORIGINAL observed QQQ/TQQQ downloader, not a rewritten
        # synthetic close or a copied signal value. Provider lag may disappear.
        rebuild()
    raise RuntimeError("OBSERVED_ETF_FROZEN_PARITY_UNRESOLVED_NO_PUBLICATION")


def main() -> None:
    signal = json.loads(SIGNAL_PATH.read_text(encoding="utf-8"))
    def load_report():
        return json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
    def rebuild():
        subprocess.run([sys.executable, "tradable_tqqq_execution_comparison.py"], check=True)
    reconcile(load_report, signal, rebuild, time.sleep)


if __name__ == "__main__":
    main()
