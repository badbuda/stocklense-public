from __future__ import annotations
COST_SENSITIVITY_BPS=(0.0,5.0,10.0,20.0)
DEFAULT_TRANSACTION_COST_BPS=5.0
EVIDENCE_CLASS="REPLAY_APPROXIMATION"
EXECUTION_PARITY=False
AUTOMATIC_MODEL_CHANGE=False

def as_dict():
 return {
  "schema_version":1,
  "cost_sensitivity_bps":list(COST_SENSITIVITY_BPS),
  "default_transaction_cost_bps":DEFAULT_TRANSACTION_COST_BPS,
  "evidence_class":EVIDENCE_CLASS,
  "full_lean_execution_parity":EXECUTION_PARITY,
  "automatic_model_change":AUTOMATIC_MODEL_CHANGE,
  "semantics":"Descriptive frozen-path replay accounting only; assumptions do not select or promote a model.",
 }
