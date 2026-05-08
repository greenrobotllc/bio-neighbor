"""
Tests for the ChEMBL mechanism / target overlap helpers (issue #53).

Focuses on the pure-logic pieces — `_aggregate_targets_by_id` and
`_shared_targets` — which earlier review feedback flagged for emitting
duplicate shared-target rows when a drug has multiple ChEMBL mechanism
rows pointing at the same gene.

Run: `python -m unittest test_drug_targets.py` from `backend/`.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import drug_targets


class TestAggregateTargetsById(unittest.TestCase):
    """`_aggregate_targets_by_id` collapses multiple rows per target."""

    def test_single_row_passes_through(self):
        out = drug_targets._aggregate_targets_by_id([
            {
                "target_chembl_id": "CHEMBL1978", "gene_symbol": "CYP19A1",
                "protein_name": "Aromatase", "action_type": "INHIBITOR",
                "mechanism_of_action": "Cytochrome P450 19A1 inhibitor",
            },
        ])
        self.assertEqual(set(out), {"CHEMBL1978"})
        self.assertEqual(out["CHEMBL1978"]["gene_symbol"], "CYP19A1")
        self.assertEqual(out["CHEMBL1978"]["action_types"], ["INHIBITOR"])

    def test_multiple_rows_same_target_dedup_action_types(self):
        out = drug_targets._aggregate_targets_by_id([
            {"target_chembl_id": "X", "action_type": "INHIBITOR",
             "mechanism_of_action": "primary mech"},
            {"target_chembl_id": "X", "action_type": "ANTAGONIST",
             "mechanism_of_action": "primary mech"},  # duplicate mech
            {"target_chembl_id": "X", "action_type": "INHIBITOR",  # duplicate action
             "mechanism_of_action": "secondary mech"},
        ])
        self.assertEqual(set(out), {"X"})
        # Action types preserved in first-seen order, deduped.
        self.assertEqual(out["X"]["action_types"], ["INHIBITOR", "ANTAGONIST"])
        # Mechanisms deduped likewise.
        self.assertEqual(
            out["X"]["mechanisms_of_action"],
            ["primary mech", "secondary mech"],
        )

    def test_rows_without_target_chembl_id_skipped(self):
        # Some ChEMBL mechanism rows have no target — skip them rather
        # than crash or stuff them into a None bucket.
        out = drug_targets._aggregate_targets_by_id([
            {"target_chembl_id": None, "action_type": "INHIBITOR"},
            {"target_chembl_id": "", "action_type": "INHIBITOR"},
            {"target_chembl_id": "X", "action_type": "INHIBITOR"},
        ])
        self.assertEqual(list(out.keys()), ["X"])

    def test_first_non_empty_gene_symbol_wins(self):
        out = drug_targets._aggregate_targets_by_id([
            {"target_chembl_id": "X", "gene_symbol": None, "protein_name": None},
            {"target_chembl_id": "X", "gene_symbol": "GENE", "protein_name": "Protein"},
            {"target_chembl_id": "X", "gene_symbol": "OTHER", "protein_name": "Other"},
        ])
        # First non-empty wins; we don't randomly flip-flop between rows.
        self.assertEqual(out["X"]["gene_symbol"], "GENE")
        self.assertEqual(out["X"]["protein_name"], "Protein")


class TestSharedTargets(unittest.TestCase):
    """`_shared_targets` emits exactly one row per shared target."""

    def test_emits_one_row_per_shared_target(self):
        # Both drugs have two mechanism rows for the same gene CHEMBL1978
        # (e.g. ChEMBL split rows by hierarchy). Expected: ONE shared
        # target row with merged action types — not four duplicates.
        targets_a = [
            {"target_chembl_id": "CHEMBL1978", "gene_symbol": "CYP19A1",
             "action_type": "INHIBITOR"},
            {"target_chembl_id": "CHEMBL1978", "gene_symbol": "CYP19A1",
             "action_type": "ANTAGONIST"},
        ]
        targets_b = [
            {"target_chembl_id": "CHEMBL1978", "gene_symbol": "CYP19A1",
             "action_type": "INHIBITOR"},
            {"target_chembl_id": "CHEMBL1978", "gene_symbol": "CYP19A1",
             "action_type": "NEGATIVE MODULATOR"},
        ]
        shared = drug_targets._shared_targets(targets_a, targets_b)
        self.assertEqual(len(shared), 1)
        row = shared[0]
        self.assertEqual(row["target_chembl_id"], "CHEMBL1978")
        self.assertEqual(row["gene_symbol"], "CYP19A1")
        # Both action types from each side are preserved (joined, since
        # the Swift contract expects strings, not lists).
        self.assertEqual(row["action_type_a"], "INHIBITOR / ANTAGONIST")
        self.assertEqual(row["action_type_b"], "INHIBITOR / NEGATIVE MODULATOR")

    def test_no_overlap_returns_empty(self):
        a = [{"target_chembl_id": "X", "action_type": "INHIBITOR"}]
        b = [{"target_chembl_id": "Y", "action_type": "INHIBITOR"}]
        self.assertEqual(drug_targets._shared_targets(a, b), [])

    def test_deterministic_order(self):
        # When multiple targets are shared, output order should be
        # stable (sorted by target_chembl_id) so snapshot/regression
        # tests don't flap and the audit's deterministic-findings
        # section reads consistently across re-runs.
        a = [
            {"target_chembl_id": "CHEMBL2", "action_type": "INHIBITOR"},
            {"target_chembl_id": "CHEMBL10", "action_type": "INHIBITOR"},
            {"target_chembl_id": "CHEMBL1", "action_type": "INHIBITOR"},
        ]
        b = a
        shared = drug_targets._shared_targets(a, b)
        # String sort: "CHEMBL1", "CHEMBL10", "CHEMBL2"
        self.assertEqual(
            [s["target_chembl_id"] for s in shared],
            ["CHEMBL1", "CHEMBL10", "CHEMBL2"],
        )


if __name__ == "__main__":
    unittest.main()
