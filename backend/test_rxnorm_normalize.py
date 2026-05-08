"""
Tests for the RxNorm name → ingredient normalization (issue #55).

Two layers:
  - Pure-logic helpers (`_group_key`, `_input_key`) — no DB, no network.
  - End-to-end `normalize_drugs()` against a temp SQLite, with the
    network-going `_live_normalize` mocked so tests are deterministic
    and offline.

Run: `python -m unittest test_rxnorm_normalize.py` from `backend/`.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import rxnorm_normalize


class TestGroupKey(unittest.TestCase):
    """`_group_key` decides the dedupe key for one normalization row."""

    def test_prefers_ingredient_rxcui_when_present(self):
        # Brand input (Arimidex) resolves to ingredient anastrozole — the
        # ingredient RXCUI is what collapses brand+generic.
        result = {"rxcui": "262485", "ingredient_rxcui": "84857", "matched": True}
        self.assertEqual(
            rxnorm_normalize._group_key(result, "Arimidex"),
            "rxcui:84857",
        )

    def test_falls_back_to_input_rxcui_when_ingredient_missing(self):
        # Combo products / multi-ingredient drugs may not have an
        # ingredient mapping — the input RXCUI is the next-best key.
        result = {"rxcui": "12345", "ingredient_rxcui": None, "matched": True}
        self.assertEqual(
            rxnorm_normalize._group_key(result, "drug"),
            "rxcui:12345",
        )

    def test_unmatched_keeps_distinct_per_drug_key(self):
        # Crucial behavior: unmatched names must NOT all collapse into
        # one bucket — each unknown name should remain its own row.
        a = {"rxcui": None, "ingredient_rxcui": None, "matched": False}
        b = {"rxcui": None, "ingredient_rxcui": None, "matched": False}
        self.assertEqual(rxnorm_normalize._group_key(a, "Foo"), "name:foo")
        self.assertEqual(rxnorm_normalize._group_key(b, "Bar"), "name:bar")
        self.assertNotEqual(
            rxnorm_normalize._group_key(a, "Foo"),
            rxnorm_normalize._group_key(b, "Bar"),
        )

    def test_input_key_lowercases_and_strips(self):
        self.assertEqual(rxnorm_normalize._input_key("  Anastrozole  "), "anastrozole")
        self.assertEqual(rxnorm_normalize._input_key("TYLENOL"), "tylenol")


class TestNormalizeDrugsCacheRoundtrip(unittest.TestCase):
    """`normalize_drugs` against a temp DB with mocked live calls."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        # Patch DB_PATH so we don't touch the production DB. The module
        # imports DB_PATH at module-load time, so we patch the attribute
        # *on the module*, not the upstream `data_loader`.
        self._patcher = patch.object(rxnorm_normalize, "DB_PATH", self.db_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.tmpdir.cleanup()

    def test_first_call_hits_live_then_caches(self):
        stub = {
            "matched": True,
            "rxcui": "202433",
            "normalized_name": "Tylenol",
            "ingredient_rxcui": "161",
            "ingredient_name": "acetaminophen",
        }
        with patch.object(
            rxnorm_normalize, "_live_normalize", return_value=stub
        ) as mock_live:
            r1 = rxnorm_normalize.normalize_drugs([{"name": "Tylenol", "chembl_id": None}])
            self.assertEqual(mock_live.call_count, 1)

            # Second call must hit cache — no additional live call.
            r2 = rxnorm_normalize.normalize_drugs([{"name": "Tylenol", "chembl_id": None}])
            self.assertEqual(mock_live.call_count, 1, "second call should be cache-only")

        self.assertEqual(r1[0]["group_key"], "rxcui:161")
        self.assertEqual(r2[0]["group_key"], "rxcui:161")

    def test_brand_and_generic_collapse_to_same_group_key(self):
        # The whole point of issue #55: "Tylenol" and "acetaminophen"
        # share the ingredient RXCUI 161, so they get the same group_key
        # and are deduped before per-drug fetches fan out.
        responses = {
            "tylenol": {
                "matched": True, "rxcui": "202433", "normalized_name": "Tylenol",
                "ingredient_rxcui": "161", "ingredient_name": "acetaminophen",
            },
            "acetaminophen": {
                "matched": True, "rxcui": "161", "normalized_name": "acetaminophen",
                "ingredient_rxcui": "161", "ingredient_name": "acetaminophen",
            },
        }
        with patch.object(
            rxnorm_normalize, "_live_normalize",
            side_effect=lambda name: responses[name.lower()],
        ):
            result = rxnorm_normalize.normalize_drugs([
                {"name": "Tylenol", "chembl_id": None},
                {"name": "acetaminophen", "chembl_id": None},
            ])
        self.assertEqual(result[0]["group_key"], result[1]["group_key"])
        self.assertEqual(result[0]["group_key"], "rxcui:161")

    def test_unmatched_drug_returns_distinct_name_key(self):
        unmatched = {
            "matched": False, "rxcui": None, "normalized_name": None,
            "ingredient_rxcui": None, "ingredient_name": None,
        }
        with patch.object(rxnorm_normalize, "_live_normalize", return_value=unmatched):
            result = rxnorm_normalize.normalize_drugs(
                [{"name": "ZzNotARealDrug", "chembl_id": None}]
            )
        self.assertFalse(result[0]["matched"])
        self.assertEqual(result[0]["group_key"], "name:zznotarealdrug")

    def test_empty_input_short_circuits(self):
        # Empty list must not even open the DB or call live — protects
        # the hot path when an audit has no drugs supplied yet.
        with patch.object(
            rxnorm_normalize, "_live_normalize",
            side_effect=AssertionError("should not be called"),
        ):
            self.assertEqual(rxnorm_normalize.normalize_drugs([]), [])

    def test_cached_negative_result_does_not_re_fetch(self):
        # We persist the negative (unmatched) case so unknown drugs
        # don't re-hit RxNorm on every audit.
        unmatched = {
            "matched": False, "rxcui": None, "normalized_name": None,
            "ingredient_rxcui": None, "ingredient_name": None,
        }
        with patch.object(
            rxnorm_normalize, "_live_normalize", return_value=unmatched
        ) as mock_live:
            rxnorm_normalize.normalize_drugs([{"name": "BogusDrug", "chembl_id": None}])
            rxnorm_normalize.normalize_drugs([{"name": "BogusDrug", "chembl_id": None}])
            self.assertEqual(mock_live.call_count, 1)

    def test_transient_lookup_error_does_NOT_cache_no_match(self):
        # A flaky-network RxNormLookupError must NOT be persisted as a
        # "matched: false" cache row — otherwise the next audit (when
        # the network is healthy) would see the cached failure and skip
        # the lookup, returning a false no-match for a real drug.
        with patch.object(
            rxnorm_normalize, "_live_normalize",
            side_effect=rxnorm_normalize.RxNormLookupError("simulated network error"),
        ) as mock_live:
            r1 = rxnorm_normalize.normalize_drugs(
                [{"name": "anastrozole", "chembl_id": None}]
            )
            # First call returned an unmatched-shaped result (so the
            # current audit keeps running) but it was NOT cached.
            self.assertFalse(r1[0]["matched"])
            # Second call must re-fetch — proves cache write was skipped.
            rxnorm_normalize.normalize_drugs(
                [{"name": "anastrozole", "chembl_id": None}]
            )
            self.assertEqual(mock_live.call_count, 2)

    def test_lookup_helpers_raise_on_transient_failure(self):
        # Direct unit test of the lookup helpers: network exceptions
        # must surface as RxNormLookupError, not as a None result that
        # callers would mistake for "no match".
        import requests as _requests
        with patch.object(
            rxnorm_normalize.requests, "get",
            side_effect=_requests.ConnectionError("simulated"),
        ):
            with self.assertRaises(rxnorm_normalize.RxNormLookupError):
                rxnorm_normalize._rxcui_lookup_exact("anything")
            with self.assertRaises(rxnorm_normalize.RxNormLookupError):
                rxnorm_normalize._rxcui_lookup_approximate("anything")

    def test_lookup_helpers_return_none_on_genuine_no_match(self):
        # Successful HTTP response with empty idGroup → genuine no-match
        # → returns None, MUST NOT raise. Distinguishes "we asked and
        # they don't have this drug" from "we couldn't reach them".
        from unittest.mock import MagicMock
        ok_empty = MagicMock(status_code=200)
        ok_empty.json.return_value = {"idGroup": {}}
        with patch.object(rxnorm_normalize.requests, "get", return_value=ok_empty):
            self.assertIsNone(rxnorm_normalize._rxcui_lookup_exact("zzznope"))

    def test_secondary_helpers_raise_on_transient(self):
        # _resolve_ingredient / _rxcui_properties / _historystatus must
        # also raise on transient errors — otherwise they silently
        # return None and `_live_normalize` builds a partial-data
        # `matched=true` row that gets cached.
        import requests as _requests
        with patch.object(
            rxnorm_normalize.requests, "get",
            side_effect=_requests.ConnectionError("simulated"),
        ):
            with self.assertRaises(rxnorm_normalize.RxNormLookupError):
                rxnorm_normalize._resolve_ingredient("12345")
            with self.assertRaises(rxnorm_normalize.RxNormLookupError):
                rxnorm_normalize._rxcui_properties("12345")
            with self.assertRaises(rxnorm_normalize.RxNormLookupError):
                rxnorm_normalize._historystatus("12345")


if __name__ == "__main__":
    unittest.main()
