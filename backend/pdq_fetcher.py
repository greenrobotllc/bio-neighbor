"""
NCI PDQ "Health Professional" treatment-summary fetcher for the Treatment
Auditor (issue #45 v2 / #49).

Pulls structured sections from cancer.gov's PDQ pages for the cancer types
listed in SLUG_BY_CANCER_TYPE_NAME, scores them against the user's stage,
stage detail, and subtype markers, and returns the top-N most relevant
sections with a per-section length cap so the resulting text fits inside an
LLM prompt without crowding out the trial digests.

Data source: https://www.cancer.gov/types/{slug}/hp/{slug}-treatment-pdq
- Public, free, updated by NCI.
- HTML is reasonably structured: H2 = top-level section, H3/H4 = subsections.
- We walk h2/h3/h4 + p/li linearly, attach text to the most-recent heading,
  and cap at MAX_TOTAL_CHARS so the audit's prompt budget stays bounded.

Public entry point: fetch_pdq_summary(...).
"""

from functools import lru_cache
import re
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


# Lowercased cancer-type name → cancer.gov URL slug. Each URL
# https://www.cancer.gov/types/{slug}/hp/{slug}-treatment-pdq is a published
# Health Professional PDQ summary.
#
# Hematologic cancers (leukemia, lymphoma) are intentionally omitted: they use
# different staging systems and per-subtype URLs (aml, all, cml, …) that don't
# follow the simple slug pattern. Audit gracefully degrades for unmapped types.
SLUG_BY_CANCER_TYPE_NAME = {
    "breast": "breast",
    "lung": "lung",
    "non-small cell lung": "non-small-cell-lung",
    "small cell lung": "small-cell-lung",
    "colorectal": "colorectal",
    "colon": "colorectal",
    "rectal": "rectal",
    "prostate": "prostate",
    "melanoma": "melanoma",
    "ovarian": "ovarian",
    "pancreatic": "pancreatic",
    "kidney": "kidney",
    "renal": "kidney",
    "bladder": "bladder",
}

PDQ_URL_TEMPLATE = "https://www.cancer.gov/types/{slug}/hp/{slug}-treatment-pdq"
USER_AGENT = "BioNeighbor-TreatmentAuditor/1.0"
FETCH_TIMEOUT_SECONDS = 15
MAX_TOTAL_CHARS = 6000   # cap on text shipped into the LLM prompt
MAX_SECTIONS = 6
MIN_PARAGRAPH_LEN = 30   # filter boilerplate / nav text

# Stage value → set of substrings likely to appear in PDQ section headings.
_STAGE_KEYWORDS = {
    "stage i": ["stage i", "stages i, ii", "early"],
    "stage ii": ["stage ii", "stages i, ii"],
    "stage iii": ["stage iii", "stages i, ii, and iii", "locoregional"],
    "stage iv": ["stage iv", "metastatic", "advanced"],
    "metastatic": ["metastatic", "stage iv", "advanced"],
    "recurrent": ["recurrent", "locoregional recurrent", "relapsed"],
}

_ALWAYS_INCLUDE_TITLE_FRAGMENTS = (
    "stage information",
    "surgical treatment",
    "radiation therapy",
    "treatment option overview",
)


def _resolve_slug(cancer_type_name: str) -> Optional[str]:
    name = (cancer_type_name or "").strip().lower()
    if not name:
        return None
    if name in SLUG_BY_CANCER_TYPE_NAME:
        return SLUG_BY_CANCER_TYPE_NAME[name]
    # Loose containment match — handles "Breast cancer", "lung carcinoma", etc.
    for key, slug in SLUG_BY_CANCER_TYPE_NAME.items():
        if key in name:
            return slug
    return None


@lru_cache(maxsize=16)
def _fetch_page_html(url: str) -> Optional[str]:
    """Process-lifetime cached HTTP fetch. PDQ pages change rarely; caching
    for the server's lifetime is safe and avoids hammering cancer.gov."""
    try:
        resp = requests.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return resp.text


def _extract_sections(html: str) -> List[Dict]:
    """Walk h2/h3/h4 + p/li in document order. Each heading is a section
    whose text is the paragraphs/list-items between it and the next heading.

    Note: An h2 that contains only h3 children will end up with empty text
    (its paragraphs all live under the child h3s). That's fine — the scorer
    selects sections by heading-level individually, not as a tree.
    """
    soup = BeautifulSoup(html, "html.parser")
    sections: List[Dict] = []
    current: Optional[Dict] = None
    parent_h2: Optional[str] = None

    def flush():
        if current is None:
            return
        current["text"] = " ".join(current["_text_parts"]).strip()
        if current["text"] or current["level"] == 2:
            sections.append(current)

    for el in soup.find_all(["h2", "h3", "h4", "p", "li"]):
        if el.name in ("h2", "h3", "h4"):
            flush()
            level = int(el.name[1])
            # Some headings contain <br> or literal newlines; collapse them.
            title = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if level == 2:
                parent_h2 = title
            current = {
                "title": title,
                "level": level,
                "parent": parent_h2 if level > 2 else None,
                "_text_parts": [],
            }
        else:
            if current is None:
                continue
            text = el.get_text(" ", strip=True)
            if text and len(text) >= MIN_PARAGRAPH_LEN:
                current["_text_parts"].append(text)
    flush()

    for s in sections:
        s.pop("_text_parts", None)
    return sections


def _normalize_marker_keywords(marker: str) -> List[str]:
    """HER2+ → ['her2+', 'her2-positive'].
    HER2- → ['her2-', 'her2-negative'].
    HER2  → ['her2'].

    When polarity is known the bare base ('her2') is intentionally omitted —
    otherwise it substring-matches the opposite-polarity heading
    ('HER2-Positive') and HER2-low variants in a HER2-negative audit."""
    base = marker.strip().lower()
    if not base:
        return []
    if base.endswith("+"):
        return [base, base[:-1] + "-positive"]
    if base.endswith("-"):
        return [base, base[:-1] + "-negative"]
    return [base]


def _score_section(
    section: Dict,
    stage: Optional[str],
    stage_detail: Optional[str],
    markers: List[str],
) -> Tuple[int, bool]:
    """Returns (score, always_include).

    Heuristic, kept readable:
      - 0    title names a polarity that conflicts with a patient marker
              (e.g. 'HER2-Positive' or 'HER2-Low' when patient is HER2-).
              Section is dropped from consideration entirely.
      - +10  title matches a stage keyword
      - +5   title matches a marker (HER2+ → 'her2-positive')
      - +5   title matches a stage_detail token
      - +1   text matches a stage_detail token
      - +2 + always_include=True  for stage-info / modality-overview sections
    """
    title_lc = section["title"].lower()
    text_lc = section.get("text", "").lower()

    if _section_marker_conflict(title_lc, markers):
        return 0, False

    always = any(frag in title_lc for frag in _ALWAYS_INCLUDE_TITLE_FRAGMENTS)
    score = 2 if always else 0

    if stage:
        for kw in _STAGE_KEYWORDS.get(stage.strip().lower(), []):
            if kw in title_lc:
                score += 10
                break

    if stage_detail:
        # Capture both prose tokens (bone, brain, liver, lymph) AND TNM-style
        # atoms (t2, n1, m0, t2a). Two complementary patterns: the first
        # matches 4+ char alpha words, the second matches letter+digit
        # combinations anywhere in the string — important because "T2N1M0" is
        # one continuous token with no word boundaries between T2, N1, M0.
        detail_lc = stage_detail.lower()
        tokens: set = set()
        tokens.update(re.findall(r"[a-z]{4,}", detail_lc))
        tokens.update(re.findall(r"[a-z]\d[a-z]?", detail_lc))
        for token in tokens:
            if token in title_lc:
                score += 5
            elif token in text_lc:
                score += 1

    for marker in markers:
        for kw in _normalize_marker_keywords(marker):
            if kw and _marker_match(kw, title_lc):
                score += 5
                break

    return score, always


# For a polarity-known patient marker (X+ or X-), section titles naming the
# opposite polarity are clinically about a different patient population.
# '-low' is treated as conflicting for BOTH polarities: HER2-low is a distinct
# therapeutic category (e.g. trastuzumab deruxtecan eligibility) that overlaps
# with but is not the same as either classical HER2-negative or HER2-positive,
# so PDQ sections titled "HER2-Low" should be picked up only when the patient
# is explicitly marked as such (not currently in the taxonomy).
_CONFLICTING_SUFFIXES = {
    "+": ["-", "-negative", "-low", "-intermediate", "-equivocal"],
    "-": ["+", "-positive", "-low", "-intermediate", "-equivocal"],
}


def _section_marker_conflict(title_lc: str, markers: List[str]) -> bool:
    """True if the section title explicitly names a polarity that conflicts
    with any of the patient's polarity-specific markers."""
    for marker in markers or []:
        base = marker.strip().lower()
        if not base or base[-1] not in ("+", "-"):
            continue
        polarity = base[-1]
        prefix = base[:-1]
        if not prefix:
            continue
        for suffix in _CONFLICTING_SUFFIXES[polarity]:
            if _marker_match(prefix + suffix, title_lc):
                return True
    return False


def _marker_match(keyword: str, title_lc: str) -> bool:
    """Word-boundary-aware substring check.

    Plain `in` lets 'her2-' match 'her2-positive' / 'her2-low' (wrong
    polarity). Anchor on word-character boundaries: the keyword itself may
    contain '+', '-', '/', etc., but it must not be immediately adjacent to
    a word character on either side. This blocks 'her2-' inside
    'her2-positive' (next char 'p' is a word char) while allowing
    'brca1/2' to match 'brca1/2-mutated' (next char '-' is a separator)."""
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, title_lc) is not None


def fetch_pdq_summary(
    cancer_type_name: str,
    stage: Optional[str] = None,
    stage_detail: Optional[str] = None,
    markers: Optional[List[str]] = None,
) -> Optional[Dict]:
    """Fetch a PDQ summary scoped to (cancer_type, stage, stage_detail, markers).

    Returns:
        {
            "slug": "breast",
            "source_url": "https://www.cancer.gov/types/breast/hp/breast-treatment-pdq",
            "stage": <echoed>,
            "stage_detail": <echoed>,
            "sections": [{"title", "level", "parent", "text"}, ...]
        }
        or None when the cancer type isn't mapped or the page can't be fetched.
    """
    slug = _resolve_slug(cancer_type_name)
    if slug is None:
        return None
    url = PDQ_URL_TEMPLATE.format(slug=slug)
    html = _fetch_page_html(url)
    if html is None:
        return None

    all_sections = _extract_sections(html)
    marker_list = markers or []
    scored: List[Tuple[int, bool, Dict]] = []
    for s in all_sections:
        score, always = _score_section(s, stage, stage_detail, marker_list)
        if score > 0:
            scored.append((score, always, s))

    # Highest-scoring first; among ties, prefer always-include overview sections.
    scored.sort(key=lambda t: (t[0], 1 if t[1] else 0), reverse=True)

    selected: List[Dict] = []
    total_chars = 0
    per_section_cap = max(800, MAX_TOTAL_CHARS // MAX_SECTIONS)
    for _score, _always, s in scored:
        if len(selected) >= MAX_SECTIONS:
            break
        text = s.get("text", "")
        if len(text) > per_section_cap:
            text = text[:per_section_cap].rsplit(" ", 1)[0] + " …"
        if total_chars + len(text) > MAX_TOTAL_CHARS:
            break
        total_chars += len(text)
        selected.append({
            "title": s["title"],
            "level": s["level"],
            "parent": s.get("parent"),
            "text": text,
        })

    if not selected:
        # Page structure changed, slug pointed somewhere unexpected, or
        # extraction returned no relevant content. Surface as pdq_unavailable
        # so the caller renders a "skipped" step rather than success-with-
        # empty-content, which the LLM has nothing to do with.
        return None

    return {
        "slug": slug,
        "source_url": url,
        "stage": stage,
        "stage_detail": stage_detail,
        "sections": selected,
    }
