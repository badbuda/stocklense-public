import copy
import unittest
from research.pit_breadth_temporal_replay_20261114 import qualify_replay

def row(day="09", split="train"):
    return {"decision_at":f"2026-11-{day}T21:00:00Z",
            "signal_known_at":f"2026-11-{day}T20:59:00Z",
            "order_at":f"2026-11-{day}T21:01:00Z",
            "fill_at":f"2026-11-{day}T21:02:00Z",
            "split":split, "source_kind":"observed_constituent_pit",
            "dataset_id":"snapshot-sha256-example"}

class TemporalReplayTests(unittest.TestCase):
    def test_valid_only_temporal(self):
        x=qualify_replay([row("09"),row("10","validation"),row("11","test")])
        self.assertEqual(x["status"],"TEMPORAL_ONLY")
        self.assertFalse(x["historical_breadth_authorized"])
        self.assertFalse(x["tax_validated"])
    def test_lookahead(self):
        x=row();x["signal_known_at"]="2026-11-09T21:01:00Z"
        self.assertEqual(qualify_replay([x])["reason"],"LOOKAHEAD_SIGNAL")
    def test_same_bar(self):
        x=row();x["order_at"]=x["decision_at"]
        self.assertEqual(qualify_replay([x])["reason"],"SAME_BAR_OR_PREORDER_FILL")
    def test_fill_before_order(self):
        x=row();x["fill_at"]=x["decision_at"]
        self.assertEqual(qualify_replay([x])["reason"],"SAME_BAR_OR_PREORDER_FILL")
    def test_split_backtrack(self):
        self.assertEqual(qualify_replay([row("09","test"),row("10","train")])["reason"],"OOS_SPLIT_BACKTRACK")
    def test_dataset_mismatch(self):
        x=row("10");x["dataset_id"]="other"
        self.assertEqual(qualify_replay([row(),x])["reason"],"MIXED_DATASET")
    def test_proxy(self):
        x=row();x["source_kind"]="qqqe_proxy"
        self.assertEqual(qualify_replay([x])["reason"],"PROXY_OR_SYNTHETIC")
    def test_duplicate(self):
        x=row()
        self.assertEqual(qualify_replay([x,copy.deepcopy(x)])["reason"],"NON_MONOTONIC_DECISION")
    def test_empty(self):
        self.assertEqual(qualify_replay([])["reason"],"EMPTY_REPLAY")
