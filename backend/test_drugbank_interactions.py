"""
Tests for the DrugBank pairwise drug-drug interaction lookup (issue #47).

XML parsing is exercised indirectly — these tests seed a temp SQLite
table directly and verify the matching/sorting/case-handling logic in
`get_pairwise_interactions`. The XML iterparse path is intentionally
not unit-tested: it'd require a multi-MB fixture and the parser is
straightforward iterparse + dict packing.

Run: `python -m unittest test_drugbank_interactions.py` from `backend/`.
"""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import drugbank_interactions


class TestSeverityInference(unittest.TestCase):
    """`_infer_severity` keyword heuristic on common DrugBank phrasings."""

    def test_severe_keywords(self):
        self.assertEqual(
            drugbank_interactions._infer_severity("This combination is contraindicated."),
            "severe",
        )
        self.assertEqual(
            drugbank_interactions._infer_severity("Serious bleeding may occur."),
            "severe",
        )
        self.assertEqual(
            drugbank_interactions._infer_severity("Major risk of QT prolongation."),
            "severe",
        )

    def test_moderate_keywords(self):
        self.assertEqual(
            drugbank_interactions._infer_severity("Monitor closely for hypotension."),
            "moderate",
        )
        self.assertEqual(
            drugbank_interactions._infer_severity("Use caution when combining."),
            "moderate",
        )

    def test_minor_keywords(self):
        self.assertEqual(
            drugbank_interactions._infer_severity("Minor reduction in absorption."),
            "minor",
        )

    def test_returns_none_when_no_keyword_matches(self):
        # Many DrugBank descriptions are bland — no severity keyword.
        # Returning None is correct: better to render "unknown" than to
        # mis-classify by guessing.
        self.assertIsNone(
            drugbank_interactions._infer_severity("The risk may be increased.")
        )

    def test_empty_string_returns_none(self):
        self.assertIsNone(drugbank_interactions._infer_severity(""))


class TestPairwiseInteractions(unittest.TestCase):
    """`get_pairwise_interactions` against a seeded in-memory DB."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self._patcher = patch.object(drugbank_interactions, "DB_PATH", self.db_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.tmpdir.cleanup()

    def _seed(self, rows):
        conn = sqlite3.connect(self.db_path)
        try:
            drugbank_interactions.ensure_interactions_table(conn)
            conn.executemany(
                "INSERT INTO drug_interactions "
                "(drug_a_id, drug_a_name, drug_b_id, drug_b_name, description, severity) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def test_unloaded_state_returns_drugbank_loaded_false(self):
        # Empty DB — `is_interactions_loaded()` returns False, and the
        # endpoint should signal "data unavailable" rather than "none
        # found". Those are very different statements clinically.
        result = drugbank_interactions.get_pairwise_interactions([
            {"name": "warfarin", "chembl_id": None, "drugbank_id": None},
        ])
        self.assertFalse(result["drugbank_loaded"])
        self.assertEqual(result["interactions"], [])
        # Unmatched should carry the input names so the UI can be honest
        # about what couldn't be checked.
        self.assertEqual(result["unmatched"], ["warfarin"])

    def test_returns_only_pairs_where_both_in_query(self):
        self._seed([
            ("DB00682", "Warfarin", "DB00945", "Aspirin", "Risk of bleeding.", "severe"),
            # Imaginarium pair must NOT appear — it's not in the query.
            ("DB00682", "Warfarin", "DB99999", "Imaginarium", "Unrelated.", None),
        ])
        result = drugbank_interactions.get_pairwise_interactions([
            {"name": "Warfarin", "chembl_id": None, "drugbank_id": None},
            {"name": "Aspirin", "chembl_id": None, "drugbank_id": None},
        ])
        self.assertTrue(result["drugbank_loaded"])
        self.assertEqual(len(result["interactions"]), 1)
        self.assertEqual(result["interactions"][0]["severity"], "severe")

    def test_severity_sort_severe_first(self):
        self._seed([
            ("DB001", "A", "DB002", "B", "minor stuff", "minor"),
            ("DB001", "A", "DB003", "C", "severe stuff", "severe"),
            ("DB002", "B", "DB003", "C", "moderate stuff", "moderate"),
        ])
        result = drugbank_interactions.get_pairwise_interactions([
            {"name": "A", "chembl_id": None, "drugbank_id": None},
            {"name": "B", "chembl_id": None, "drugbank_id": None},
            {"name": "C", "chembl_id": None, "drugbank_id": None},
        ])
        # Severe first, then moderate, then minor — patient-facing UI
        # should always lead with the most actionable rows.
        self.assertEqual(
            [i["severity"] for i in result["interactions"]],
            ["severe", "moderate", "minor"],
        )

    def test_case_insensitive_name_match(self):
        # User input casing shouldn't matter — DrugBank stores names in
        # specific casing but users type whatever.
        self._seed([
            ("DB00682", "Warfarin", "DB00945", "Aspirin", "Bleeding.", "severe"),
        ])
        result = drugbank_interactions.get_pairwise_interactions([
            {"name": "WARFARIN", "chembl_id": None, "drugbank_id": None},
            {"name": "aspirin", "chembl_id": None, "drugbank_id": None},
        ])
        self.assertEqual(len(result["interactions"]), 1)
        self.assertEqual(result["unmatched"], [])

    def test_unmatched_names_returned_separately(self):
        self._seed([
            ("DB00682", "Warfarin", "DB00945", "Aspirin", "Bleeding.", "severe"),
        ])
        result = drugbank_interactions.get_pairwise_interactions([
            {"name": "Warfarin", "chembl_id": None, "drugbank_id": None},
            {"name": "DefinitelyNotADrug", "chembl_id": None, "drugbank_id": None},
        ])
        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(result["unmatched"], ["DefinitelyNotADrug"])
        # Only one drug matched — there is no second drug to pair with.
        self.assertEqual(len(result["interactions"]), 0)

    def test_user_input_name_preserved_in_output(self):
        # The UI shows the user's typed name, not DrugBank's canonical
        # spelling — easier to read and less surprising.
        self._seed([
            ("DB00682", "Warfarin", "DB00945", "Aspirin", "Bleeding.", "severe"),
        ])
        result = drugbank_interactions.get_pairwise_interactions([
            {"name": "warfarin", "chembl_id": None, "drugbank_id": None},
            {"name": "ASPIRIN", "chembl_id": None, "drugbank_id": None},
        ])
        ix = result["interactions"][0]
        self.assertIn(ix["drug_a_name"], {"warfarin", "ASPIRIN"})
        self.assertIn(ix["drug_b_name"], {"warfarin", "ASPIRIN"})


if __name__ == "__main__":
    unittest.main()
