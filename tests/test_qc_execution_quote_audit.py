"""Unit tests for offline QuantConnect order/submission quote forensics."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from qc_execution_quote_audit import audit


def fixture(*, price=101.0, bid=100.0, ask=101.0, last=100.0,
            qty=10.0, time="2024-08-29T13:32:00Z"):
    order = {
        "status": 3, "symbol": {"value": "TQQQ"}, "quantity": qty,
        "price": price, "time": time,
        "orderSubmissionData": {"bidPrice": bid, "askPrice": ask, "lastPrice": last},
    }
    return {
        "orders": {"1": order},
        "charts": {
            "SL724_QC_EXECUTION_PRICES": {"series": {}},
            "SL724_P0_FEATURES": {"series": {"close": {"values": [[1, 2]]}}},
        },
        "statistics": {"Total Orders": "1"},
        "runtimeStatistics": {"X": "Y"},
    }


class TestNativeOrderQuotes(unittest.TestCase):
    def evaluate(self, new, prior=None):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "new.json"
            path.write_text(json.dumps(new))
            if prior is None:
                return audit(path)
            old = Path(t) / "old.json"
            old.write_text(json.dumps(prior))
            return audit(path, old)

    def test_buy_uses_ask_not_last_as_side_quote(self):
        value = fixture()
        report = self.evaluate(value, value)
        tqqq = report["by_symbol"]["TQQQ"]
        self.assertEqual(tqqq["fill_vs_side_quote_directional"]["median_bps"], 0)
        self.assertAlmostEqual(
            tqqq["fill_vs_last_directional_NOT_SLIPPAGE"]["median_bps"], 100)
        self.assertTrue(report["rerun_comparison"]["all_checked_identical"])
        self.assertFalse(report["claims"]["measured_broker_slippage"])

    def test_sell_uses_bid_and_loss_sign(self):
        report = self.evaluate(fixture(qty=-3, price=99, bid=100, ask=101))
        tqqq = report["by_symbol"]["TQQQ"]
        self.assertAlmostEqual(
            tqqq["fill_vs_side_quote_directional"]["median_bps"], 100)
        self.assertEqual(tqqq["sides"]["SELL"], 1)

    def test_chart_requires_exact_instant_not_date(self):
        data = fixture()
        data["charts"]["SL724_QC_EXECUTION_PRICES"]["series"] = {
            "TQQQ_0932": {"values": [[1724938260, 100]]}}
        self.assertEqual(
            self.evaluate(data)["by_symbol"]["TQQQ"]["exact_timestamp_chart_join_count"], 0)

    def test_quote_outlier_blocks_clean_claim(self):
        data = fixture(bid=100, ask=103, price=108, last=101)
        report = self.evaluate(data)
        self.assertEqual(report["outlier_count"], 1)
        self.assertFalse(report["quality_gates"]["no_spread_or_fill_quote_outliers_over_50bps"])
        self.assertEqual(report["status"], "AUDITED_WITH_EXECUTION_REALISM_BLOCKERS")

    def test_changed_order_detected_on_second_run(self):
        before = fixture()
        after = deepcopy(before)
        after["orders"]["1"]["price"] = 102
        self.assertFalse(self.evaluate(after, before)["rerun_comparison"]["all_checked_identical"])

    def test_crossed_quote_rejected(self):
        with self.assertRaisesRegex(ValueError, "CROSSED_SUBMISSION_QUOTES"):
            self.evaluate(fixture(bid=102, ask=101))

    def test_missing_quote_prevents_complete_coverage(self):
        data = fixture()
        data["orders"]["2"] = {
            "status": 3, "symbol": {"value": "QQQ"},
            "quantity": 4, "price": 200, "time": "2024-08-29T13:32:00Z"}
        report = self.evaluate(data)
        self.assertEqual(report["orders_with_usable_side_quotes"], 1)
        self.assertFalse(report["quality_gates"]["complete_filled_order_quote_coverage"])
