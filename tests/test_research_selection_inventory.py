import json
from research_selection_inventory import build


def test_inventory_does_not_claim_independent_holdout(tmp_path):
    results = tmp_path / "results.json"
    queue = tmp_path / "queue.json"
    results.write_text(json.dumps({"results": [
        {"status": "NOT_VALIDATED", "technical_result": {"experiment_id": "SL9-001"}},
        {"status": "REJECTED", "technical_result": {"experiment_id": "SL9-001"}},
    ]}))
    queue.write_text(json.dumps({"experiments": [{"experiment_id": "SL9-001"}]}))
    result = build(results_path=str(results), queue_path=str(queue),
                   out=str(tmp_path / "out.json"), public_out=str(tmp_path / "public.json"))
    assert result["recorded_research_results"] == 2
    assert result["queued_hypotheses"] == 1
    assert result["per_experiment_result_counts"]["SL9-001"] == 2
    assert result["status"] == "SELECTION_INDEPENDENCE_NOT_ESTABLISHED"
    assert result["holdout_never_reused_proven"] is False
    assert result["live_trading_authorized"] is False
    assert (tmp_path / "out.json").read_bytes() == (tmp_path / "public.json").read_bytes()
