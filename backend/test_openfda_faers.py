"""
Tests for the OpenFDA FAERS lookup (issue #46).

Covers two distinct concerns:
  - `_symptom_to_term_match` precedence (exact > substring > token).
    This matcher is the load-bearing piece — it decides which top
    reaction term gets paired with the user's free-text symptom.
  - `get_top_events_for_drug` cache roundtrip + `get_drug_event_panel`
    end-to-end shape, both with the network call mocked.

Run: `python -m unittest test_openfda_faers.py` from `backend/`.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import openfda_faers


class TestSymptomMatcher(unittest.TestCase):
    """`_symptom_to_term_match` precedence: exact > substring-in-term >
    term-in-symptom > token overlap."""

    EVENTS = [
        {"term": "FATIGUE", "count": 386},
        {"term": "FATIGUE INCREASED", "count": 50},
        {"term": "PERIPHERAL NEUROPATHY", "count": 200},
        {"term": "RASH", "count": 100},
        {"term": "SKIN RASH", "count": 30},
    ]

    def test_exact_case_insensitive_wins_over_substring(self):
        # Both "FATIGUE" (exact) and "FATIGUE INCREASED" (symptom is a
        # substring) match — exact must win regardless of count.
        match = openfda_faers._symptom_to_term_match("fatigue", self.EVENTS)
        self.assertEqual(match["term"], "FATIGUE")
        self.assertEqual(match["count"], 386)

    def test_symptom_substring_of_term(self):
        # "neuropathy" appears inside "PERIPHERAL NEUROPATHY".
        match = openfda_faers._symptom_to_term_match("neuropathy", self.EVENTS)
        self.assertEqual(match["term"], "PERIPHERAL NEUROPATHY")

    def test_exact_match_wins_when_user_provides_full_term(self):
        # User typed "skin rash" — both "RASH" (term-in-symptom) and
        # "SKIN RASH" (exact) match. Exact wins.
        match = openfda_faers._symptom_to_term_match("skin rash", self.EVENTS)
        self.assertEqual(match["term"], "SKIN RASH")

    def test_term_substring_of_symptom_falls_through_to_match(self):
        # User typed "severe rash"; "RASH" is a substring of the symptom.
        # No exact or symptom-in-term match, so term-in-symptom should fire.
        match = openfda_faers._symptom_to_term_match(
            "severe rash", [{"term": "RASH", "count": 99}]
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["term"], "RASH")

    def test_no_match_returns_none(self):
        self.assertIsNone(
            openfda_faers._symptom_to_term_match("hippopotamus", self.EVENTS)
        )

    def test_empty_inputs_return_none(self):
        self.assertIsNone(openfda_faers._symptom_to_term_match("", self.EVENTS))
        self.assertIsNone(openfda_faers._symptom_to_term_match("fatigue", []))


class TestPanelCacheRoundtrip(unittest.TestCase):
    """`get_top_events_for_drug` and `get_drug_event_panel` shape +
    cache behavior, with the network call mocked."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self._patcher = patch.object(openfda_faers, "DB_PATH", self.db_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.tmpdir.cleanup()

    def test_first_call_hits_live_then_caches(self):
        fake_events = [{"term": "NAUSEA", "count": 100}]
        fake_total = 9999
        with patch.object(
            openfda_faers, "_live_top_events", return_value=(fake_events, fake_total)
        ) as mock_live:
            r1 = openfda_faers.get_top_events_for_drug("tamoxifen", limit=10)
            r2 = openfda_faers.get_top_events_for_drug("tamoxifen", limit=10)

        self.assertEqual(mock_live.call_count, 1, "second call must be cache-only")
        self.assertEqual(r1["top_events"], r2["top_events"])
        self.assertEqual(r1["total_reports"], 9999)

    def test_panel_combines_per_drug_with_symptom_matches(self):
        # tamoxifen's top reactions include FATIGUE — should match.
        # anastrozole's only event is NAUSEA — symptom "fatigue" should
        # NOT match, so we expect exactly one symptom-match row.
        def stub(drug_name, limit):
            if drug_name.lower() == "tamoxifen":
                return ([{"term": "FATIGUE", "count": 200}], 1000)
            return ([{"term": "NAUSEA", "count": 50}], 500)

        with patch.object(openfda_faers, "_live_top_events", side_effect=stub):
            panel = openfda_faers.get_drug_event_panel(
                drugs=[
                    {"name": "tamoxifen", "chembl_id": None},
                    {"name": "anastrozole", "chembl_id": None},
                ],
                symptoms=["fatigue"],
            )

        # Per-drug rows preserved in input order — this is what the PDF
        # report iterates over.
        names = [p["drug_name"] for p in panel["per_drug"]]
        self.assertEqual(names, ["tamoxifen", "anastrozole"])

        self.assertEqual(len(panel["symptom_matches"]), 1)
        m = panel["symptom_matches"][0]
        self.assertEqual(m["drug_name"], "tamoxifen")
        self.assertEqual(m["matched_term"], "FATIGUE")
        self.assertEqual(m["rank_in_top"], 1)
        self.assertEqual(m["total_reports"], 1000)

    def test_empty_drug_name_returns_empty_panel(self):
        # Defensive: an empty drug name shouldn't blow up, just no-op.
        result = openfda_faers.get_top_events_for_drug("", limit=10)
        self.assertEqual(result["top_events"], [])
        self.assertEqual(result["total_reports"], 0)

    def test_transient_failure_does_NOT_cache(self):
        # A flaky-network failure (signaled by `_live_top_events`
        # returning None) must NOT be persisted to the 7-day cache —
        # otherwise the next 7 audits would see a stale "no events"
        # panel for a drug that genuinely has reports.
        with patch.object(
            openfda_faers, "_live_top_events", return_value=None
        ) as mock_live:
            r1 = openfda_faers.get_top_events_for_drug("tamoxifen", limit=10)
            r2 = openfda_faers.get_top_events_for_drug("tamoxifen", limit=10)
        self.assertEqual(mock_live.call_count, 2, "second call must re-fetch")
        # Caller still gets a usable empty panel for the current request.
        self.assertEqual(r1["top_events"], [])
        self.assertEqual(r2["top_events"], [])


if __name__ == "__main__":
    unittest.main()
