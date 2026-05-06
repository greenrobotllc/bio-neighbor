"""
ClinicalTrials.gov v2 fetcher for the drug detail page's Trial Outcomes section.

Pulls NCT IDs from ChEMBL drug_indication, then batch-fetches each trial's
arms + reported primary outcomes. Surfaces multi-arm comparisons (e.g.
"abemaciclib + NSAI: PFS 28.18 mo  vs  placebo + NSAI: PFS 14.76 mo")
which is the data the user asked about — same regimen plus/minus a drug.

Public API:
    fetch_trials_for_drug(chembl_id, max_trials=15) -> List[Dict]
"""

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


def fetch_trials_for_drug(chembl_id: str, max_trials: int = 15) -> List[Dict]:
    """
    Pull NCT IDs from ChEMBL drug_indication for this drug and fetch each
    from ClinicalTrials.gov v2 in parallel. Returns trials sorted with
    "results posted" first (most informative), then by NCT ID. Capped at
    max_trials so the page doesn't drown in 50+ trials.
    """
    nct_ids = fetch_nct_ids_for_drug(chembl_id)
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

    # Surface the most informative trials first: those with reported numeric
    # outcomes for multiple arms (true treatment comparisons). Then trials
    # with any results, then anything else. Stable by NCT ID within tier.
    def _sort_key(t: Dict):
        outcomes = t.get("primary_outcomes") or []
        # A trial is "comparable" when at least one primary outcome has
        # measurements for >=2 arms — that's the apples-to-apples comparison
        # the user is after ("regimen X vs regimen X+Y").
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

    trials.sort(key=_sort_key)
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
