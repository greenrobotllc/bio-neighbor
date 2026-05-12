"""
Tests for the pdq_fetcher polarity-aware marker matching (issue #101).

Locks down the regex word-boundary semantics and the polarity-conflict
exclusion so a HER2-negative audit doesn't pull in HER2-Positive / HER2-Low
sections, and the symmetric case for HER2+.

Pure-logic, no DB, no network.

Run: `python -m unittest test_pdq_fetcher.py` from `backend/`.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pdq_fetcher import (
    _marker_match,
    _normalize_marker_keywords,
    _score_section,
    _section_marker_conflict,
)


class TestMarkerMatch(unittest.TestCase):
    """`_marker_match` is the word-boundary-aware substring check that
    keeps `her2-` from leaking into `her2-positive` / `her2-low`."""

    def test_polarity_keyword_does_not_match_opposite_polarity_title(self):
        # The original bug: bare-base 'her2' substring-matched HER2-Positive
        # and HER2-Low titles for a HER2-negative patient.
        self.assertFalse(_marker_match("her2-", "metastatic her2-positive breast cancer"))
        self.assertFalse(_marker_match("her2-", "metastatic her2-low breast cancer"))

    def test_polarity_keyword_matches_same_polarity_title(self):
        # Note: the bare polarity keyword 'her2-' WILL NOT match inside
        # 'her2-negative' because 'n' is a trailing word char — same boundary
        # logic that blocks the cross-polarity leak. Same-polarity matching
        # relies on the expanded keyword from `_normalize_marker_keywords`.
        self.assertTrue(_marker_match("her2-negative", "her2-negative metastatic breast cancer"))
        self.assertTrue(_marker_match("her2-positive", "her2-positive metastatic breast cancer"))
        # The bare polarity token matches when it stands alone in the title.
        self.assertTrue(_marker_match("her2-", "patient is her2- and pr-positive"))
        self.assertTrue(_marker_match("her2+", "patient is her2+ pre-treatment"))

    def test_exact_token_match(self):
        # 'her2-' as a bare token (followed by whitespace) must still match.
        self.assertTrue(_marker_match("her2-", "her2-"))
        self.assertTrue(_marker_match("her2-", "patient is her2- and pr-positive"))

    def test_partial_token_does_not_match(self):
        # Keyword is longer than what's in the title.
        self.assertFalse(_marker_match("her2-", "her2"))

    def test_polarity_sign_at_token_boundary(self):
        # 'her2+' at start, end, and in the middle of a title.
        self.assertTrue(_marker_match("her2+", "her2+ breast cancer"))
        self.assertTrue(_marker_match("her2+", "metastatic her2+"))
        # Adjacent word char must block; '-' is a non-word separator so
        # bare 'her2' DOES match 'her2-positive' (permissive by design —
        # polarity exclusion is enforced at the `_section_marker_conflict`
        # layer, not here).
        self.assertFalse(_marker_match("her2", "her2gene amplification"))
        self.assertTrue(_marker_match("her2", "her2-positive breast cancer"))

    def test_slash_in_keyword_matches_with_trailing_separator(self):
        # Regression that caught a too-strict first-pass regex: 'brca1/2'
        # must match 'brca1/2-mutated' (the trailing '-' is a separator,
        # not a polarity flip).
        self.assertTrue(_marker_match("brca1/2", "brca1/2-mutated ovarian cancer"))

    def test_hyphenated_compound_marker(self):
        # MSI-H must not match MSI-L, and FLT3-ITD must not match FLT3-TKD.
        self.assertTrue(_marker_match("msi-h", "msi-h colorectal cancer"))
        self.assertFalse(_marker_match("msi-h", "msi-l colorectal cancer"))
        self.assertTrue(_marker_match("flt3-itd", "flt3-itd positive aml"))
        self.assertFalse(_marker_match("flt3-itd", "flt3-tkd positive aml"))

    def test_punctuation_boundaries(self):
        # Parens and slashes act as natural separators on either side.
        self.assertTrue(_marker_match("del(17p)", "del(17p) cll"))
        self.assertTrue(_marker_match("1p/19q codel", "1p/19q codel oligodendroglioma"))

    def test_adjacent_word_character_blocks_match(self):
        # 'her2' must not match inside a longer word like 'her2gene'.
        self.assertFalse(_marker_match("her2", "her2gene amplification"))
        # Same for trailing word char on a polarity token.
        self.assertFalse(_marker_match("her2-", "her2-positiveness scale"))


class TestNormalizeMarkerKeywords(unittest.TestCase):
    """Keyword expansion for polarity-suffixed markers."""

    def test_negative_polarity_expansion(self):
        # Bare base ('her2') is intentionally omitted — it would substring-leak
        # into 'her2-positive'/'her2-low' headings.
        self.assertEqual(
            sorted(_normalize_marker_keywords("HER2-")),
            ["her2-", "her2-negative"],
        )

    def test_positive_polarity_expansion(self):
        self.assertEqual(
            sorted(_normalize_marker_keywords("HER2+")),
            ["her2+", "her2-positive"],
        )

    def test_unqualified_marker_keeps_bare_form(self):
        # Without polarity, the bare token is the only keyword.
        self.assertEqual(_normalize_marker_keywords("HER2"), ["her2"])

    def test_empty_marker(self):
        self.assertEqual(_normalize_marker_keywords(""), [])
        self.assertEqual(_normalize_marker_keywords("   "), [])


class TestSectionMarkerConflict(unittest.TestCase):
    """`_section_marker_conflict` drops sections whose title names a polarity
    that conflicts with any of the patient's polarity-specific markers."""

    def test_her2_negative_patient_conflicts_with_positive_section(self):
        self.assertTrue(
            _section_marker_conflict(
                "metastatic her2-positive breast cancer", ["HER2-"]
            )
        )

    def test_her2_negative_patient_conflicts_with_low_section(self):
        # HER2-low is a distinct therapeutic category, not a synonym for
        # HER2-negative.
        self.assertTrue(
            _section_marker_conflict(
                "metastatic her2-low breast cancer", ["HER2-"]
            )
        )

    def test_her2_positive_patient_conflicts_with_negative_section(self):
        self.assertTrue(
            _section_marker_conflict(
                "metastatic her2-negative breast cancer", ["HER2+"]
            )
        )

    def test_her2_positive_patient_conflicts_with_low_section(self):
        # '-low' conflicts both polarities — different therapeutic category.
        self.assertTrue(
            _section_marker_conflict(
                "metastatic her2-low breast cancer", ["HER2+"]
            )
        )

    def test_same_polarity_section_does_not_conflict(self):
        self.assertFalse(
            _section_marker_conflict(
                "metastatic her2-negative breast cancer", ["HER2-"]
            )
        )
        self.assertFalse(
            _section_marker_conflict(
                "metastatic her2-positive breast cancer", ["HER2+"]
            )
        )

    def test_marker_neutral_section_does_not_conflict(self):
        # Section title with no polarity mention should pass through.
        self.assertFalse(
            _section_marker_conflict(
                "treatment option overview for metastatic breast cancer",
                ["HER2-"],
            )
        )

    def test_overlapping_markers_any_conflict_drops(self):
        # If ANY of the patient's markers conflicts, the section is dropped.
        # Patient is ER+/PR+/HER2-; section mentions HER2-positive → drop.
        self.assertTrue(
            _section_marker_conflict(
                "metastatic her2-positive breast cancer",
                ["ER+", "PR+", "HER2-"],
            )
        )

    def test_unqualified_marker_does_not_trigger_conflict(self):
        # An unqualified 'HER2' marker has no polarity, so it can't define
        # a conflict — leave the section in.
        self.assertFalse(
            _section_marker_conflict(
                "her2-positive breast cancer", ["HER2"]
            )
        )

    def test_no_markers_no_conflict(self):
        self.assertFalse(_section_marker_conflict("her2-positive breast cancer", []))
        self.assertFalse(_section_marker_conflict("her2-positive breast cancer", None))

    def test_non_polarity_markers_skipped(self):
        # Markers without +/- suffix (MSI-H, BRCA1/2, BRAF V600E) shouldn't
        # produce conflict keywords.
        self.assertFalse(
            _section_marker_conflict(
                "her2-positive breast cancer",
                ["MSI-H", "BRCA1/2", "BRAF V600E"],
            )
        )


class TestScoreSectionPolarityIntegration(unittest.TestCase):
    """End-to-end: `_score_section` should return 0 for conflict-dropped
    sections and a positive score for relevant ones."""

    def test_her2_negative_patient_drops_her2_positive_section(self):
        section = {"title": "Metastatic HER2-Positive Breast Cancer", "text": ""}
        score, _ = _score_section(
            section, stage="Stage IV", stage_detail="", markers=["HER2-"]
        )
        self.assertEqual(score, 0)

    def test_her2_negative_patient_drops_her2_low_section(self):
        section = {"title": "Metastatic HER2-Low Breast Cancer", "text": ""}
        score, _ = _score_section(
            section, stage="Stage IV", stage_detail="", markers=["HER2-"]
        )
        self.assertEqual(score, 0)

    def test_her2_negative_patient_keeps_her2_negative_section(self):
        section = {"title": "Metastatic HER2-Negative Breast Cancer", "text": ""}
        score, _ = _score_section(
            section, stage="Stage IV", stage_detail="", markers=["HER2-"]
        )
        # +10 for "metastatic" matching Stage IV, +5 for HER2- marker match.
        self.assertGreater(score, 0)

    def test_no_markers_no_section_dropped_by_conflict(self):
        # Regression-safe: without markers, polarity-named sections still
        # score normally (no conflict check fires).
        section = {"title": "Metastatic HER2-Positive Breast Cancer", "text": ""}
        score, _ = _score_section(
            section, stage="Stage IV", stage_detail="", markers=[]
        )
        self.assertGreater(score, 0)


if __name__ == "__main__":
    unittest.main()
