"""CI regression checks for SL-62. No network or broker access."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.overnight_session_timing_study import (
    SOURCE, load, replay, evaluate, report, target
)
from observed_etf_two_question_audit import _run


class OvernightResearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load(SOURCE)
        cls.rows = cls.source["daily"]

    def test_source_prior_signal_and_boundaries(self):
        self.assertEqual(len(self.rows), 4191)
        self.assertTrue(all(r["signal"] < r["date"] for r in self.rows))
        self.assertEqual(self.rows[-1]["date"], "2026-10-09")

    def test_frozen8_exact_path_parity(self):
        reproduced = replay(self.rows)
        baseline = _run(self.rows, variant="frozen")
        self.assertEqual(reproduced["orders"], 147)
        for x, y in zip(reproduced["navs"], baseline["navs"]):
            self.assertAlmostEqual(x / y, 1.0, places=9)

    def test_cash_and_target_exposure(self):
        self.assertEqual(target(0, .8, "StockLens"), {"QQQ": 0., "TQQQ": 0.})
        self.assertAlmostEqual(sum(target(3, 1., "StockLens").values()), .985)
        self.assertAlmostEqual(sum(target(3, .5, "StockLens").values()), .4925)
        with self.assertRaises(ValueError):
            target(3., 1.1, "StockLens")

    def test_execution_friction_costs_and_gross_night(self):
        gross = replay(self.rows, day_fraction=0, night_fraction=1,
                       fee=0, slip=0)
        modeled = replay(self.rows, day_fraction=0, night_fraction=1,
                         fee=2, slip=10)
        self.assertGreater(gross["cagr"], 0.35)
        self.assertLess(modeled["cagr"], 0)
        self.assertGreater(modeled["orders"], 8000)
        self.assertGreater(modeled["modeled_fees"], 0)
        self.assertGreater(modeled["modeled_slippage"], 0)

    def test_entire_grid_and_reports(self):
        results = evaluate(self.source)
        self.assertEqual(len(results["results"]), 12)
        self.assertEqual(results["status"], "RETROSPECTIVE_DAILY_PROXY_ONLY")
        self.assertIn("overnight_stocklens", report(results))
        self.assertFalse(results["broker_orders_allowed"])


if __name__ == "__main__":
    unittest.main()
