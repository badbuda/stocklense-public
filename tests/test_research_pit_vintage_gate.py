"""Adversarial synthetic ALFRED fixtures, not historical PIT or alpha."""
import copy
import hashlib
import json
import unittest
from research_pit_vintage_gate import audit_snapshot

def sample(series="T10Y3M"):
    return {"series_id": series, "response": {
        "realtime_start": "2018-02-06", "realtime_end": "2018-02-06",
        "observation_start": "2018-02-01", "observation_end": "2018-02-06",
        "units": "lin", "output_type": 1, "file_type": "json",
        "order_by": "observation_date", "sort_order": "asc",
        "count": 2, "offset": 0, "limit": 100000,
        "observations": [
            {"date": "2018-02-01", "realtime_start": "2018-02-06",
             "realtime_end": "2018-02-06", "value": "1.50"},
            {"date": "2018-02-05", "realtime_start": "2018-02-06",
             "realtime_end": "2018-02-06", "value": "1.60"}]}}

def raw(x):
    return json.dumps(x, sort_keys=True).encode()

class VintageGateTests(unittest.TestCase):
    def test_pinned_series_never_certified(self):
        for series in ("T10Y3M", "BAMLH0A0HYM2"):
            b = raw(sample(series))
            result = audit_snapshot(b, trade_date="2018-02-07", expected_series=series)
            self.assertEqual(result["raw_envelope_sha256"], hashlib.sha256(b).hexdigest())
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["pre2023_observation_rows_not_first_seen_proof"], 2)
            self.assertEqual(result["economically_qualified_rows"], 0)
            self.assertFalse(result["historical_first_seen_independently_certified"])
            self.assertFalse(result["automatic_promotion"])

    def test_missing_values_are_not_filled(self):
        x = sample(); x["response"]["observations"][0]["value"] = "."
        result = audit_snapshot(raw(x), trade_date="2018-02-07", expected_series="T10Y3M")
        self.assertEqual((result["missing_rows"], result["nonmissing_rows"]), (1, 1))
        self.assertEqual(result["economically_qualified_rows"], 0)

    def test_self_asserted_first_seen_does_not_promote(self):
        x = sample(); x["independent_first_seen_verified"] = True
        x["response"]["independent_release_timestamp"] = "2018-02-06T00:01:00Z"
        result = audit_snapshot(raw(x), trade_date="2018-02-07", expected_series="T10Y3M")
        self.assertFalse(result["historical_first_seen_independently_certified"])

    def test_adversarial_mutations_fail_closed(self):
        x = sample()
        cases = [
            (lambda y: y.pop("response"), "missing native response"),
            (lambda y: y.update(series_id="BAMLH0A0HYM2"), "wrong pinned series"),
            (lambda y: y["response"].update(units="pc1"), "transformed"),
            (lambda y: y["response"].update(output_type=2), "transformed"),
            (lambda y: y["response"].update(offset=1), "paginated"),
            (lambda y: y["response"].update(count=3), "paginated"),
            (lambda y: y["response"].update(limit=1), "paginated"),
            (lambda y: y["response"].update(realtime_end="2018-02-07"), "multi-day"),
            (lambda y: y["response"].update(sort_order="desc"), "ordering"),
            (lambda y: y["response"]["observations"][1].update(date="2018-02-01"), "duplicate"),
            (lambda y: y["response"]["observations"][0].update(date="2018-02-09"), "future"),
            (lambda y: y["response"]["observations"][0].update(value="NaN"), "invalid series"),
            (lambda y: y["response"]["observations"][0].update(value=True), "invalid series"),
            (lambda y: y["response"]["observations"][0].update(value="-500"), "invalid series"),
            (lambda y: y["response"]["observations"][0].update(realtime_end="2018-02-05"), "as-of window"),
        ]
        for change, error in cases:
            y = copy.deepcopy(x); change(y)
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                audit_snapshot(raw(y), trade_date="2018-02-07", expected_series="T10Y3M")

    def test_no_same_day_asof_at_0931(self):
        with self.assertRaisesRegex(ValueError, "future or multi-day"):
            audit_snapshot(raw(sample()), trade_date="2018-02-06", expected_series="T10Y3M")

    def test_reject_duplicate_json_keys_and_constants(self):
        x = raw(sample()).decode().replace('"series_id": "T10Y3M"',
              '"series_id": "T10Y3M", "series_id": "T10Y3M"')
        with self.assertRaisesRegex(ValueError, "invalid raw JSON"):
            audit_snapshot(x.encode(), trade_date="2018-02-07", expected_series="T10Y3M")
        with self.assertRaisesRegex(ValueError, "invalid raw JSON"):
            audit_snapshot(b'{"series_id":NaN}', trade_date="2018-02-07", expected_series="T10Y3M")
