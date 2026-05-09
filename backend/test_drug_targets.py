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
        # Sorted, deduped — order is independent of input row order so
        # snapshots stay stable even if ChEMBL re-shuffles its results.
        self.assertEqual(out["X"]["action_types"], ["ANTAGONIST", "INHIBITOR"])
        self.assertEqual(
            out["X"]["mechanisms_of_action"],
            ["primary mech", "secondary mech"],
        )

    def test_aggregation_is_input_order_independent(self):
        # Same rows in two different orders must produce identical
        # aggregated output — that's the whole point of sorting.
        rows_a = [
            {"target_chembl_id": "X", "action_type": "INHIBITOR",
             "mechanism_of_action": "mech1"},
            {"target_chembl_id": "X", "action_type": "ANTAGONIST",
             "mechanism_of_action": "mech2"},
        ]
        rows_b = list(reversed(rows_a))
        self.assertEqual(
            drug_targets._aggregate_targets_by_id(rows_a),
            drug_targets._aggregate_targets_by_id(rows_b),
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
        # Joined in sorted order — deterministic regardless of how
        # ChEMBL ordered the underlying mechanism rows.
        self.assertEqual(row["action_type_a"], "ANTAGONIST / INHIBITOR")
        self.assertEqual(row["action_type_b"], "INHIBITOR / NEGATIVE MODULATOR")

    def test_mechanism_of_action_is_symmetric_union(self):
        # Drug A has only mech1, drug B has only mech2. The shared
        # target's mechanism_of_action must include BOTH (sorted) —
        # the previous "A wins" behavior would silently drop drug B's
        # contribution and produce different output if A and B were
        # swapped.
        targets_a = [
            {"target_chembl_id": "X", "mechanism_of_action": "drug A's mech",
             "action_type": "INHIBITOR"},
        ]
        targets_b = [
            {"target_chembl_id": "X", "mechanism_of_action": "drug B's mech",
             "action_type": "INHIBITOR"},
        ]
        shared_ab = drug_targets._shared_targets(targets_a, targets_b)
        shared_ba = drug_targets._shared_targets(targets_b, targets_a)
        # Both directions produce the same mechanism_of_action.
        self.assertEqual(shared_ab[0]["mechanism_of_action"],
                         shared_ba[0]["mechanism_of_action"])
        # And it covers BOTH drugs' mechanisms.
        self.assertEqual(
            shared_ab[0]["mechanism_of_action"],
            "drug A's mech / drug B's mech",
        )

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


class TestLiveFetchDrugMechanisms(unittest.TestCase):
    """Control flow around `_live_fetch_drug_mechanisms` and the
    parent-ID fallback."""

    def test_transient_child_does_not_consult_parent(self):
        # When the direct mechanism query errors transiently, we MUST
        # NOT fall back to the parent compound's mechanism list.
        # Caching a parent-derived `[]` as the child's answer would
        # freeze "no mechanisms" forever even though the child's real
        # answer is unknown.
        from unittest.mock import patch
        # First call (direct) returns None → transient.
        # Second call (parent) would return [] if reached — but we
        # expect it NOT to be reached.
        call_log = []

        def mock_query(chembl_id):
            call_log.append(chembl_id)
            return None  # always transient

        with patch.object(drug_targets, "_query_mechanism_endpoint",
                          side_effect=mock_query) as mock_q, \
             patch.object(drug_targets, "_resolve_parent_chembl_id",
                          side_effect=AssertionError("parent must not be consulted")):
            result = drug_targets._live_fetch_drug_mechanisms("CHEMBL1")
        self.assertIsNone(result, "transient child must propagate as None")
        self.assertEqual(mock_q.call_count, 1, "parent fallback must be skipped")

    def test_definite_empty_child_consults_parent(self):
        # When the direct query returned a definite [] (succeeded with
        # no rows), the parent fallback DOES run — that's the salt-form
        # case the fallback exists for.
        from unittest.mock import patch

        def mock_query(chembl_id):
            if chembl_id == "CHEMBL_CHILD":
                return []  # definite empty
            return [{"target_chembl_id": "T", "action_type": "INHIBITOR",
                     "mechanism_of_action": "from parent"}]

        with patch.object(drug_targets, "_query_mechanism_endpoint",
                          side_effect=mock_query) as mock_q, \
             patch.object(drug_targets, "_resolve_parent_chembl_id",
                          return_value="CHEMBL_PARENT"):
            result = drug_targets._live_fetch_drug_mechanisms("CHEMBL_CHILD")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["mechanism_of_action"], "from parent")
        self.assertEqual(mock_q.call_count, 2, "parent fallback was consulted")


class TestExceptionNarrowing(unittest.TestCase):
    """Catch tuple in `_query_mechanism_endpoint` etc. should swallow
    expected ChEMBL/network errors but propagate genuine programming
    bugs so they're not silenced."""

    def test_request_exception_caught(self):
        # ConnectionError subclasses RequestException — should be
        # caught and return None (transient signal).
        from unittest.mock import patch, MagicMock
        import requests
        mock_mech = MagicMock()
        mock_mech.filter.side_effect = requests.ConnectionError("simulated")
        with patch.object(drug_targets.new_client, "mechanism", mock_mech):
            self.assertIsNone(drug_targets._query_mechanism_endpoint("CHEMBL1"))

    def test_unexpected_exception_propagates(self):
        # A KeyError (programming bug) must NOT be swallowed by the
        # narrowed catch — that's the whole point of moving away from
        # `except Exception`.
        from unittest.mock import patch, MagicMock
        mock_mech = MagicMock()
        mock_mech.filter.side_effect = KeyError("programming bug")
        with patch.object(drug_targets.new_client, "mechanism", mock_mech):
            with self.assertRaises(KeyError):
                drug_targets._query_mechanism_endpoint("CHEMBL1")


if __name__ == "__main__":
    unittest.main()
