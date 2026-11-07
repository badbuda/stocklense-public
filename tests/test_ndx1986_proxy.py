import hashlib
import unittest
from datetime import date, timedelta

from research.ndx1986_proxy import parse_fred_csv, build


class Ndx1986ResearchTests(unittest.TestCase):
    def test_fred_missing_values_and_provenance(self):
        rows = parse_fred_csv(b"DATE,NASDAQ100\n1986-01-02,131.25\n1986-01-03,.\n1986-01-06,130.55\n")
        self.assertEqual(rows, [("1986-01-02", 131.25), ("1986-01-06", 130.55)])
        with self.assertRaisesRegex(ValueError, "FRED_DATES_NOT_UNIQUE_SORTED"):
            parse_fred_csv(b"DATE,NASDAQ100\n1986-01-06,131\n1986-01-02,130\n")
        with self.assertRaisesRegex(ValueError, "FRED_NASDAQ100_COLUMN_MISSING"):
            parse_fred_csv(b"DATE,WRONG\n1986-01-02,131\n")

    def test_retroactive_warmup_and_prior_close(self):
        days=[(date(1986,1,2)+timedelta(days=i)).isoformat() for i in range(280)]
        rows=[(day, 130+i*.1) for i,day in enumerate(days)]
        d=build(rows,source_sha256=hashlib.sha256(b"fixture").hexdigest())
        self.assertEqual(d["period"]["source_start"], "1986-01-02")
        self.assertEqual(d["period"]["first_investable"], days[253])
        self.assertTrue(all(r["l"] is None for r in d["rows"][:253]))
        self.assertEqual(d["rows"][253]["signal"],days[252])
        self.assertIn(d["rows"][253]["l"],(0.0,1.25,2.0,3.0))
        self.assertEqual(d["strategy_semantics"],"RETROACTIVE_RULE_APPLICATION_NOT_FROZEN_2009_REPLAY")
        self.assertFalse(any("TQQQ" in r for r in d["rows"]))


if __name__=="__main__":
    unittest.main()
