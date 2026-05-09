"""
ClinicalTrials.gov v2 fetcher for the drug detail page's Trial Outcomes section.

Pulls NCT IDs from ChEMBL drug_indication, then batch-fetches each trial's
arms + reported primary outcomes. Surfaces multi-arm comparisons (e.g.
"abemaciclib + NSAI: PFS 28.18 mo  vs  placebo + NSAI: PFS 14.76 mo")
which is the data the user asked about — same regimen plus/minus a drug.

Public API:
    fetch_trials_for_drug(chembl_id, max_trials=15) -> List[Dict]
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import requests

from chembl_drug_detail import fetch_nct_ids_for_drug


CT_GOV_V2 = "https://clinicaltrials.gov/api/v2/studies"
TRIAL_FIELDS = (
    "protocolSection.identificationModule,"
    "protocolSection.statusModule,"
    "protocolSection.designModule,"
    "protocolSection.armsInterventionsModule,"
    "resultsSection"
)
PER_TRIAL_TIMEOUT = 10  # seconds
MAX_PARALLEL = 5  # concurrent CT.gov requests

# Retry knobs for the modality search. CT.gov occasionally returns 5xx /
# 429 under load; retrying with backoff converts a transient outage from a
# failed audit step into a slightly slower one. Capped at 3 attempts so a
# truly broken upstream still fails reasonably quickly.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.5  # seconds; multiplied by 2**attempt
_RETRY_JITTER_MAX = 0.1  # seconds; uniform [0, this)


def _ct_get_with_retries(
    url: str,
    *,
    params: Dict,
    timeout: int,
    condition: str,
    modality: str,
) -> "requests.Response":
    """GET `url` with bounded exponential-backoff retries on transient
    failures (RequestException, HTTP 429, HTTP 5xx). Returns a 200
    `requests.Response`; raises `RuntimeError` for any non-200 outcome —
    permanent (other 4xx) immediately, transient after retries are exhausted.

    Kept private to this module — the modality search is the only caller
    that needs retry semantics; `fetch_trial` deliberately swallows errors
    per its own contract."""
    last_exc: Optional[BaseException] = None
    last_resp: Optional["requests.Response"] = None

    for attempt in range(_RETRY_MAX_ATTEMPTS):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_exc = e
            last_resp = None
        else:
            if resp.status_code == 200:
                return resp
            # Permanent failure (other 4xx) — fail fast, no retries.
            if resp.status_code != 429 and not (500 <= resp.status_code < 600):
                raise RuntimeError(
                    f"ClinicalTrials.gov returned HTTP {resp.status_code} for "
                    f"condition={condition!r} modality={modality!r}"
                )
            last_resp = resp
            last_exc = None

        if attempt + 1 < _RETRY_MAX_ATTEMPTS:
            delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, _RETRY_JITTER_MAX)
            time.sleep(delay)

    # Exhausted retries.
    if last_resp is not None:
        raise RuntimeError(
            f"ClinicalTrials.gov returned HTTP {last_resp.status_code} for "
            f"condition={condition!r} modality={modality!r}"
            f" (after {_RETRY_MAX_ATTEMPTS} attempts)"
        )
    # last_exc must be set: every attempt either returned a response or
    # raised a RequestException.
    raise RuntimeError(
        f"ClinicalTrials.gov request failed for "
        f"condition={condition!r} modality={modality!r}"
        f" after {_RETRY_MAX_ATTEMPTS} attempts: {last_exc}"
    ) from last_exc


def _trial_sort_key(t: Dict):
    """Shared ordering for fetched trials. Surfaces the most informative
    first: trials with reported numeric outcomes across multiple arms (true
    apples-to-apples regimen comparisons), then any-results, then trials with
    more arms, with a stable NCT-ID tiebreak."""
    outcomes = t.get("primary_outcomes") or []
    is_comparable = any(
        len(o.get("arm_results") or []) >= 2 for o in outcomes
    )
    n_armed = len(t.get("arms") or [])
    return (
        not is_comparable,        # comparable trials first
        not t.get("has_results"), # then any-results
        -n_armed,                 # then more arms = more interesting
        t.get("nct_id") or "",
    )


def _strip_intervention_prefix(name: str) -> str:
    """Trial intervention names come like "Drug: Abemaciclib" — strip the kind prefix."""
    for prefix in ("Drug: ", "Biological: ", "Procedure: ", "Device: ", "Other: ", "Combination Product: "):
        if name.startswith(prefix):
            return name[len(prefix):].strip()
    return name.strip()


def parse_trial(raw: Dict) -> Dict:
    """Normalize a CT.gov v2 study payload into the flat shape we surface to the UI."""
    proto = raw.get("protocolSection") or {}
    results = raw.get("resultsSection") or {}

    ident = proto.get("identificationModule") or {}
    status = proto.get("statusModule") or {}
    arms_mod = proto.get("armsInterventionsModule") or {}
    om_mod = results.get("outcomeMeasuresModule") or {}

    arms = []
    for arm in arms_mod.get("armGroups") or []:
        arms.append({
            "label": arm.get("label"),
            "type": arm.get("type"),
            "interventions": [
                _strip_intervention_prefix(i)
                for i in arm.get("interventionNames") or []
                if i
            ],
        })

    primary_outcomes: List[Dict] = []
    for m in om_mod.get("outcomeMeasures") or []:
        if (m.get("type") or "").upper() != "PRIMARY":
            continue
        groups = {g.get("id"): g.get("title") for g in m.get("groups") or []}
        # Flatten classes → categories → measurements; we only show the first
        # class/category so the UI stays readable. Trials with subgroup
        # breakdowns will lose the subgroups, which is fine for an at-a-glance.
        per_arm: List[Dict] = []
        classes = m.get("classes") or []
        if classes:
            categories = classes[0].get("categories") or []
            if categories:
                for meas in categories[0].get("measurements") or []:
                    per_arm.append({
                        "arm_label": groups.get(meas.get("groupId")) or "?",
                        "value": meas.get("value"),
                        "lower": meas.get("lowerLimit"),
                        "upper": meas.get("upperLimit"),
                    })
        primary_outcomes.append({
            "title": m.get("title"),
            "param_type": m.get("paramType"),
            "unit": m.get("unitOfMeasure"),
            "arm_results": per_arm,
        })

    has_results = bool(om_mod.get("outcomeMeasures"))

    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "status": status.get("overallStatus"),
        "phase": (proto.get("designModule") or {}).get("phases") or [],
        "arms": arms,
        "primary_outcomes": primary_outcomes,
        "has_results": has_results,
    }


def fetch_trial(nct_id: str, timeout: int = PER_TRIAL_TIMEOUT) -> Optional[Dict]:
    """Fetch a single trial. Returns None on any error so callers can ignore failures."""
    url = f"{CT_GOV_V2}/{nct_id}?fields={TRIAL_FIELDS}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        return parse_trial(resp.json())
    except Exception as e:
        print(f"   ⚠️  CT.gov fetch error for {nct_id}: {e}")
        return None


def fetch_trials_for_drug(
    chembl_id: str,
    max_trials: int = 15,
    condition_keywords: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Pull NCT IDs from ChEMBL drug_indication for this drug and fetch each
    from ClinicalTrials.gov v2 in parallel. Returns trials sorted with
    "results posted" first (most informative), then by NCT ID. Capped at
    max_trials so the page doesn't drown in 50+ trials. Non-positive or
    non-int max_trials returns [] — mirrors the guard in
    fetch_modality_trials so negative values can't tail-slice candidates.

    `condition_keywords` is forwarded to `fetch_nct_ids_for_drug` to
    constrain the per-drug pull to indications matching the patient's
    cancer (Treatment Auditor use case — see fetch_nct_ids_for_drug
    docstring).
    """
    if not isinstance(max_trials, int) or max_trials <= 0:
        return []

    nct_ids = fetch_nct_ids_for_drug(chembl_id, condition_keywords=condition_keywords)
    if not nct_ids:
        return []

    # Over-fetch slightly: many trials lack reported results, and we want to
    # surface the ones that do.
    candidates = nct_ids[:max_trials * 2]

    trials: List[Dict] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        for parsed in executor.map(fetch_trial, candidates):
            if parsed:
                trials.append(parsed)

    trials.sort(key=_trial_sort_key)
    return trials[:max_trials]


"""
Modality-keyed search.

For the Treatment Auditor v2: instead of (or in addition to) fetching trials
linked to a specific drug via ChEMBL drug_indication, search ClinicalTrials.gov
by condition + intervention. This surfaces multi-arm modality trials for a
cancer subtype regardless of the patient's drug list.

Public API: fetch_modality_trials(condition, modality, max_trials=10)
"""

# Maps the Treatment Auditor's modality keys to the `query.intr` value that
# CT.gov v2 accepts. For chemotherapy and targeted therapy, plain-text
# matching against the intervention-name field works well — both are drug
# interventions and the term itself disambiguates. For surgery and radiation
# we use CT.gov's field-expression syntax `AREA[InterventionType]<TYPE>`
# which constrains to trials whose interventions are tagged with that type
# (PROCEDURE / RADIATION). The PROCEDURE filter alone still surfaces
# drug-arm-comparison trials that list surgery as one step (most modern
# breast / colon trials are multimodal), so for surgery we additionally
# require the intervention name to match a cancer-type-specific surgical
# term (mastectomy, lobectomy, etc.) when one of the per-cancer term lists
# applies. See `_surgical_terms_for_condition` below.
# Field expression docs: https://clinicaltrials.gov/data-api/api
_MODALITY_INTERVENTION_TERMS = {
    "radiation": "AREA[InterventionType]RADIATION",
    "surgery": "AREA[InterventionType]PROCEDURE",
    "chemotherapy": "chemotherapy",
    "targeted": "targeted therapy",
}

# Per-cancer-type surgical procedure names. Used to refine the surgery-modality
# CT.gov query from `AREA[InterventionType]PROCEDURE` (which matches any
# procedure-tagged trial — too broad, includes biopsies / port placements /
# imaging-guided procedures alongside drug-arm trials) to the same filter
# AND a name-match against the cancer-specific surgical vocabulary.
#
# Keys are lowercase substrings matched against the CT.gov condition string
# (e.g. "Breast Neoplasms", "Adenocarcinoma of Lung"). First-substring-match
# wins; cancers without an entry fall back to the unrestricted PROCEDURE
# filter so we don't silently drop surgical signal for cancers we haven't
# enumerated. Hand-coded for now; #75 tracks migrating these to PDQ-derived
# extraction so the lists update with NCI rather than this file.
_SURGICAL_TERMS_BY_CANCER = {
    "breast": [
        "mastectomy", "lumpectomy",
        "sentinel lymph node biopsy", "axillary lymph node dissection",
        "breast-conserving surgery",
    ],
    "lung": [
        "lobectomy", "pneumonectomy", "wedge resection", "segmentectomy",
        "VATS",
    ],
    "melanoma": [
        "wide local excision", "sentinel lymph node biopsy", "lymphadenectomy",
    ],
    "colorectal": [
        "colectomy", "hemicolectomy", "proctectomy",
        "low anterior resection", "abdominoperineal resection",
        "total mesorectal excision",
    ],
    "colon": ["colectomy", "hemicolectomy"],
    "rectal": ["proctectomy", "low anterior resection", "abdominoperineal resection"],
    "pancrea": [  # matches "pancreatic", "pancreas"
        "whipple", "pancreaticoduodenectomy", "distal pancreatectomy",
        "total pancreatectomy",
    ],
    "renal": ["nephrectomy", "partial nephrectomy", "radical nephrectomy"],
    "kidney": ["nephrectomy", "partial nephrectomy"],
    "prostate": ["prostatectomy", "radical prostatectomy"],
    "ovarian": [
        "hysterectomy", "salpingo-oophorectomy", "omentectomy", "debulking",
        "cytoreductive surgery",
    ],
    "bladder": [
        "cystectomy", "radical cystectomy", "transurethral resection", "TURBT",
    ],
    "gastric": ["gastrectomy", "partial gastrectomy", "total gastrectomy"],
    "stomach": ["gastrectomy"],
    "hepatocellular": ["hepatectomy", "liver resection", "partial hepatectomy"],
    "liver": ["hepatectomy", "liver resection"],
    "glioma": ["craniotomy", "tumor resection", "tumour resection"],
    "brain": ["craniotomy", "tumor resection"],
}


def _surgical_terms_for_condition(condition: str) -> Optional[List[str]]:
    """Return the per-cancer surgical-term list when the supplied condition
    matches a cancer type we've enumerated. None means 'fall back to the
    unrestricted PROCEDURE filter' — used both for cancers we haven't
    mapped (heme malignancies don't get surgery as a primary modality
    anyway) and for unrecognised condition strings."""
    cond = (condition or "").lower()
    for key, terms in _SURGICAL_TERMS_BY_CANCER.items():
        if key in cond:
            return terms
    return None


def _surgery_query_intr(condition: str) -> str:
    """Build the `query.intr` value for the surgery modality. When the
    cancer type matches a known surgical-term list, combine the procedure
    type filter with a name-OR clause; otherwise fall back to the type
    filter alone."""
    base = "AREA[InterventionType]PROCEDURE"
    terms = _surgical_terms_for_condition(condition)
    if not terms:
        return base
    # Multi-word terms need quotes so CT.gov treats them as phrases rather
    # than four ANDed bare tokens.
    quoted = [f'"{t}"' if " " in t else t for t in terms]
    return f"{base} AND ({' OR '.join(quoted)})"

# Pagination knobs for the modality search. Surveying multiple pages lets the
# multi-arm/has-results sort pick from a deeper pool than a single 20-row page
# can offer; the hard cap keeps cost bounded when a condition has thousands of
# hits (e.g. "breast cancer + chemotherapy").
_MODALITY_PAGE_SIZE = 100
_MODALITY_MAX_PAGES = 3
_MODALITY_HARD_CAP = 300


def fetch_modality_trials(
    condition: str,
    modality: str,
    max_trials: int = 10,
    stage: Optional[str] = None,
) -> List[Dict]:
    """Search CT.gov v2 for trials matching `condition` + the intervention
    term mapped from `modality`. Returns parsed trials in the same shape as
    `fetch_trials_for_drug`, sorted with multi-arm comparable outcomes first.

    `modality` must be one of: radiation, surgery, chemotherapy, targeted.
    `stage` (optional) is appended to `query.term` to bias ranking toward
    stage-relevant trials without hard-filtering — passing "Stage IV" or
    "metastatic" surfaces trials that mention those terms anywhere in the
    study record. Free-text stage_detail is intentionally NOT used as a
    query term (too noisy).
    Whitespace-only conditions and non-positive `max_trials` return [].
    """
    modality_key = (modality or "").strip().lower()
    intervention = _MODALITY_INTERVENTION_TERMS.get(modality_key)
    condition_norm = (condition or "").strip()
    if not intervention or not condition_norm:
        return []
    # Reject non-int / non-positive max_trials so downstream slicing
    # (trials[:max_trials]) is well-defined.
    if not isinstance(max_trials, int) or max_trials <= 0:
        return []

    # Surgery modality: refine the generic PROCEDURE filter with cancer-
    # type-specific procedure names when we have a list for this cancer.
    # Falls back to the unrestricted filter for cancers we haven't
    # enumerated (mostly heme — surgery isn't primary for those anyway).
    if modality_key == "surgery":
        intervention = _surgery_query_intr(condition_norm)

    base_params = {
        "query.cond": condition_norm,
        "query.intr": intervention,
        "fields": TRIAL_FIELDS,
        "pageSize": str(_MODALITY_PAGE_SIZE),
        # Prefer trials that have completed and reported results — the audit
        # cares about outcomes, not active recruitment.
        "filter.overallStatus": "COMPLETED|TERMINATED|ACTIVE_NOT_RECRUITING",
    }
    stage_norm = (stage or "").strip()
    if stage_norm:
        base_params["query.term"] = stage_norm

    # Paginate so the sort picks from a deeper pool than CT.gov's default
    # first-page relevance ordering. Stops early when (a) no more pages,
    # (b) hit the hard cap, or (c) reached MAX_PAGES. Each page is fetched
    # via _ct_get_with_retries so transient 429/5xx and transport blips
    # don't fail the whole audit step; permanent errors still propagate.
    all_studies: List[Dict] = []
    next_token: Optional[str] = None
    for _page in range(_MODALITY_MAX_PAGES):
        params = dict(base_params)
        if next_token:
            params["pageToken"] = next_token
        resp = _ct_get_with_retries(
            CT_GOV_V2,
            params=params,
            timeout=PER_TRIAL_TIMEOUT,
            condition=condition_norm,
            modality=modality,
        )
        payload = resp.json()
        page_studies = payload.get("studies") or []
        all_studies.extend(page_studies)
        next_token = payload.get("nextPageToken")
        if not next_token or len(all_studies) >= _MODALITY_HARD_CAP:
            break

    trials: List[Dict] = []
    # Narrow to data-shape errors only: a record that doesn't match the
    # expected CT.gov schema is logged-and-skipped, but unrelated programmer
    # errors (NameError, ImportError, etc.) propagate so they can be fixed.
    parse_errors = (KeyError, TypeError, ValueError, AttributeError, IndexError)
    for raw in all_studies:
        try:
            trials.append(parse_trial(raw))
        except parse_errors as e:
            # Log so unexpected schema changes / bad records are diagnosable
            # rather than invisibly dropped. Keeps `print` style consistent
            # with the rest of this module (no logger configured here).
            #
            # Drill into the nested NCT ID with isinstance guards at every
            # level — a non-dict at any step (string, list, None, …) would
            # otherwise raise inside this except handler and abort the whole
            # parse loop. We'd rather log "unknown" and keep going.
            nct_id = "unknown"
            proto = raw.get("protocolSection") if isinstance(raw, dict) else None
            ident = proto.get("identificationModule") if isinstance(proto, dict) else None
            candidate = ident.get("nctId") if isinstance(ident, dict) else None
            if isinstance(candidate, str) and candidate:
                nct_id = candidate
            print(f"   ⚠️  Failed to parse trial {nct_id} ({condition_norm} / {modality}): {e}")
            continue

    trials.sort(key=_trial_sort_key)
    return trials[:max_trials]


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("chembl_id")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    trials = fetch_trials_for_drug(args.chembl_id, max_trials=args.limit)
    print(f"Fetched {len(trials)} trials")
    print(json.dumps(trials, indent=2)[:5000])
