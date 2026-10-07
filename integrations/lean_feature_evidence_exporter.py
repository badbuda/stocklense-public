# StockLens Frozen 8.0 — LEAN identical-input evidence exporter
# Integration module: call record(...) once per decision session using the exact
# feature values and state that the frozen LEAN algorithm itself used.
# This module does not compute features or alter trading decisions.
from __future__ import annotations
import csv, io

COLUMNS=("date","close","sma50","sma200","vol20","mom12","level","defense","leverage")

class LeanFeatureEvidenceExporter:
    def __init__(self):
        self._rows=[]

    def record(self, *, date, close, sma50, sma200, vol20, mom12, level, defense, leverage):
        self._rows.append({
            "date":date.strftime("%Y-%m-%d") if hasattr(date,"strftime") else str(date)[:10],
            "close":repr(float(close)),"sma50":repr(float(sma50)),"sma200":repr(float(sma200)),
            "vol20":repr(float(vol20)),"mom12":repr(float(mom12)),"level":str(int(level)),
            "defense":"true" if bool(defense) else "false","leverage":repr(float(leverage)),
        })

    def csv_text(self):
        s=io.StringIO(newline="");w=csv.DictWriter(s,fieldnames=COLUMNS,lineterminator="\n")
        w.writeheader();w.writerows(self._rows);return s.getvalue()

    def emit_object_store(self, algorithm, key="stocklens/qc_lean_daily_features.csv"):
        text=self.csv_text()
        if not algorithm.ObjectStore.Save(key,text):
            raise RuntimeError("LEAN_FEATURE_EXPORT_SAVE_FAILED")
        algorithm.Debug("STOCKLENS_FEATURE_EXPORT key=%s rows=%d" % (key,len(self._rows)))
        return key

# Wiring contract (inside the frozen LEAN algorithm, observational only):
# Initialize: self._sl_evidence = LeanFeatureEvidenceExporter()
# After the algorithm has computed the exact decision-session inputs/state:
# self._sl_evidence.record(date=self.Time.date(), close=close, sma50=sma50,
#   sma200=sma200, vol20=vol20, mom12=mom12, level=level,
#   defense=defense, leverage=target_leverage)
# OnEndOfAlgorithm: self._sl_evidence.emit_object_store(self)
#
# IMPORTANT: export the values already used by LEAN. Do not recompute indicators
# in this exporter. The resulting CSV is evidence, not a new signal path.
