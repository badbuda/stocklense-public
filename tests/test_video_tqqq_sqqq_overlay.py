"""Guard the video-overlay experiment against core drift and lookahead."""
import unittest
from research.video_tqqq_sqqq_overlay import (
    load, moving_average, feature_rows, leverage_for, replay, evaluate,
    SOURCE_SHA, MODES,
)


class VideoOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = load()
        cls.rows = cls.raw["daily"]

    def test_source_is_real_etf_snapshot(self):
        self.assertEqual(self.raw["snapshot_sha256"], SOURCE_SHA)
        self.assertEqual(len(self.rows), 4191)
        self.assertEqual(self.raw["instruments"], ["QQQ", "TQQQ"])
        self.assertFalse("SQQQ" in self.raw["instruments"])

    def test_baseline_terminal_and_trade_count_match_frozen(self):
        ours = replay(self.rows, "frozen", lag=0, slippage=10)
        original = self.raw["without_contributions"]["strategy"]
        self.assertAlmostEqual(ours["ending_equity"], original["ending_equity"], places=3)
        self.assertEqual(ours["trades"], original["trades"])
        self.assertEqual(ours["trades"], 147)

    def test_sma_causality_at_execution_open(self):
        rows = [dict(r) for r in self.rows]
        closes, m20, m50 = feature_rows(rows)
        i = 500
        before = [leverage_for(mode, rows, i, 1, closes, m20, m50, None)
                  for mode in MODES[:6]]
        rows[i]["qc"] *= 1000
        closes2, m20b, m50b = feature_rows(rows)
        after = [leverage_for(mode, rows, i, 1, closes2, m20b, m50b, None)
                 for mode in MODES[:6]]
        self.assertEqual(before, after, "Must not use same-day close before OPEN")

    def test_sleeve_is_funded_not_leveraged_outside_portfolio(self):
        core_cash = replay(self.rows, "80_core_20_cash", lag=1, slippage=10)
        swing = replay(self.rows, "80_core_20_swing_sma50", lag=1, slippage=10)
        self.assertGreater(swing["round_trips"], 1000)
        self.assertLess(swing["ending_equity"], 1e12)
        self.assertGreater(core_cash["ending_equity"], 0)

    def test_lock_baseline_and_preliminary_sma_negative_result(self):
        base = replay(self.rows, "frozen", lag=1, slippage=10)
        candidate = replay(self.rows, "50_half_premium", lag=1, slippage=10)
        self.assertAlmostEqual(100 * base["cagr"], 37.49969, places=3)
        self.assertLess(candidate["cagr"], base["cagr"])
        self.assertGreater(candidate["trades"], base["trades"])


if __name__ == "__main__":
    unittest.main()
