"""
ChEMBL drug-detail fetcher used by the v2 Cancer Research drug detail page.

Combines two ChEMBL calls into a single structured payload:
  - new_client.molecule (properties, synonyms, structures, hierarchy)
  - new_client.drug_indication (per-indication phase + references)

Salt-form handling: when the queried ChEMBL ID is a salt (e.g.
CHEMBL3707266 = RIBOCICLIB SUCCINATE) and molecule_hierarchy.parent_chembl_id
differs, we also fetch the parent and merge — properties/synonyms come from
the parent compound (canonical), SMILES is kept from the salt (so similarity
runs on the as-administered structure).

Public API:
    fetch_drug_detail(chembl_id) -> Dict | None     # full payload, ready for JSON
    fetch_smiles(chembl_id) -> Optional[str]        # cheap SMILES-only lookup
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, List, Optional

try:
    from chembl_webresource_client.new_client import new_client
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False
    new_client = None


CHEMBL_QUERY_TIMEOUT = 20  # seconds, per ChEMBL call

# Synonym types we surface in the UI. RESEARCH_CODE is included but the
# frontend collapses it under a "+N more" disclosure.
DISPLAYED_SYN_TYPES = {
    "TRADE_NAME", "INN", "USAN", "BAN", "JAN", "ATC",
    "MERCK_INDEX", "RESEARCH_CODE",
}


def _run_with_timeout(query_fn, timeout: int = CHEMBL_QUERY_TIMEOUT):
    """Run a ChEMBL query in a worker thread with a hard timeout.

    The executor is *not* used as a context manager — `__exit__` would call
    `shutdown(wait=True)` and block on the worker thread even after a timeout,
    re-introducing the hang we're trying to avoid. On timeout we cancel the
    future (best effort) and shut the executor down with `wait=False`, leaving
    the worker thread to finish in the background.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(query_fn)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        future.cancel()
        raise
    finally:
        executor.shutdown(wait=False)


def _fetch_molecule_raw(chembl_id: str) -> Optional[Dict]:
    """Fetch a single molecule record from ChEMBL."""
    if not CHEMBL_AVAILABLE or new_client is None:
        return None
    try:
        results = _run_with_timeout(
            lambda: list(new_client.molecule.filter(molecule_chembl_id=chembl_id)[:1])
        )
        return results[0] if results else None
    except FuturesTimeoutError:
        print(f"   ⚠️  ChEMBL molecule lookup timed out for {chembl_id}")
        return None
    except Exception as e:
        print(f"   ⚠️  ChEMBL molecule lookup error for {chembl_id}: {e}")
        return None


def _fetch_indications_raw(chembl_id: str, limit: int = 200) -> List[Dict]:
    """Fetch all drug_indication rows for a molecule from ChEMBL."""
    if not CHEMBL_AVAILABLE or new_client is None:
        return []
    try:
        return _run_with_timeout(
            lambda: list(
                new_client.drug_indication.filter(molecule_chembl_id=chembl_id)
                .only([
                    "molecule_chembl_id", "max_phase_for_ind",
                    "mesh_heading", "mesh_id", "efo_term", "efo_id",
                    "indication_refs",
                ])[:limit]
            )
        )
    except FuturesTimeoutError:
        print(f"   ⚠️  ChEMBL drug_indication lookup timed out for {chembl_id}")
        return []
    except Exception as e:
        print(f"   ⚠️  ChEMBL drug_indication lookup error for {chembl_id}: {e}")
        return []


def _coerce_int(value) -> Optional[int]:
    """ChEMBL returns numeric fields as strings (e.g. '4.0'). Coerce safely."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_synonyms(raw_synonyms: List[Dict]) -> List[Dict]:
    """
    Dedupe synonyms by (name, type), preserve original order, and drop empties.
    Each row in raw_synonyms looks like:
        {'molecule_synonym': 'Lee-011', 'syn_type': 'OTHER', 'synonyms': 'LEE-011'}
    The `synonyms` field is the canonical display form per ChEMBL.
    """
    seen = set()
    out: List[Dict] = []
    for s in raw_synonyms or []:
        name = (s.get("synonyms") or s.get("molecule_synonym") or "").strip()
        syn_type = (s.get("syn_type") or "OTHER").strip().upper()
        if not name:
            continue
        key = (name.lower(), syn_type)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "type": syn_type})
    return out


def _normalize_properties(raw_props: Optional[Dict]) -> Dict:
    """Pick the small set of properties we surface, coerced to numbers."""
    raw = raw_props or {}
    return {
        "molecular_weight": _coerce_float(raw.get("full_mwt") or raw.get("mw_freebase")),
        "alogp": _coerce_float(raw.get("alogp")),
        "molecular_formula": raw.get("full_molformula"),
        "hba": _coerce_int(raw.get("hba")),
        "hbd": _coerce_int(raw.get("hbd")),
        "psa": _coerce_float(raw.get("psa")),
        "ro5_violations": _coerce_int(raw.get("num_ro5_violations")),
        "rotatable_bonds": _coerce_int(raw.get("rtb")),
        "qed_weighted": _coerce_float(raw.get("qed_weighted")),
        "aromatic_rings": _coerce_int(raw.get("aromatic_rings")),
        "heavy_atoms": _coerce_int(raw.get("heavy_atoms")),
    }


def _normalize_indications(raw_indications: List[Dict]) -> List[Dict]:
    """
    Dedupe by mesh_heading (case-insensitive) — ChEMBL files multiple
    drug_indication rows per MeSH heading, one per EFO term mapping. From a
    user's perspective these are the same indication. Keep highest max_phase
    and sum ref counts; preserve the most-clinically-advanced row's EFO/IDs.
    Sort by max_phase desc, then ref_count desc, then mesh_heading asc.
    """
    grouped: Dict[str, Dict] = {}
    for r in raw_indications or []:
        mesh_heading = (r.get("mesh_heading") or "").strip()
        if not mesh_heading:
            continue
        key = mesh_heading.lower()
        phase = _coerce_int(r.get("max_phase_for_ind")) or 0
        refs = r.get("indication_refs") or []
        ref_count = len(refs)

        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {
                "mesh_heading": mesh_heading,
                "mesh_id": r.get("mesh_id"),
                "efo_term": r.get("efo_term"),
                "efo_id": r.get("efo_id"),
                "max_phase": phase,
                "ref_count": ref_count,
            }
        else:
            # Promote the row with the higher phase as the canonical EFO mapping.
            if phase > existing["max_phase"]:
                existing["max_phase"] = phase
                existing["efo_term"] = r.get("efo_term") or existing["efo_term"]
                existing["efo_id"] = r.get("efo_id") or existing["efo_id"]
                existing["mesh_id"] = r.get("mesh_id") or existing["mesh_id"]
            existing["ref_count"] += ref_count

    rows = list(grouped.values())
    rows.sort(
        key=lambda x: (
            -(x["max_phase"] or 0),
            -(x["ref_count"] or 0),
            (x["mesh_heading"] or "").lower(),
        )
    )
    return rows


def fetch_nct_ids_for_drug(
    chembl_id: str,
    condition_keywords: Optional[List[str]] = None,
) -> List[str]:
    """
    Return all unique NCT IDs (clinicaltrials.gov references) for a drug,
    walking ChEMBL drug_indication.indication_refs across every indication.
    Used by clinical_trials.fetch_trials_for_drug to seed the trial pull.

    When the supplied id is a salt form (e.g. CHEMBL3707266 RIBOCICLIB
    SUCCINATE), ChEMBL files most drug_indication rows under the parent
    compound (CHEMBL3545110 RIBOCICLIB). Without this fallback, a Treatment
    Auditor input with the salt's ChEMBL ID returns zero trials and the
    per-drug summary step skips it entirely. We always merge in the parent's
    NCTs when the parent differs.

    `condition_keywords` (optional) restricts the indication walk to rows
    whose mesh_heading or efo_term contains any of the supplied keywords
    (case-insensitive substring). Used by the Treatment Auditor so a
    HER2+ breast-cancer audit doesn't surface ribociclib trials for
    BRAF-mutant melanoma. If filtering produces zero matches we fall back
    to the unfiltered list — better to surface partly-relevant trials
    than to silently lose all per-drug evidence for rare cancer types
    that ChEMBL doesn't yet tag.
    """
    indications = list(_fetch_indications_raw(chembl_id) or [])

    mol = _fetch_molecule_raw(chembl_id)
    parent_id = ((mol or {}).get("molecule_hierarchy") or {}).get("parent_chembl_id")
    if parent_id and parent_id != chembl_id:
        indications.extend(_fetch_indications_raw(parent_id) or [])

    if condition_keywords:
        normalized_keywords = [
            stripped.lower()
            for k in condition_keywords
            if k and (stripped := k.strip())
        ]
        if normalized_keywords:
            def _matches(ind: Dict) -> bool:
                haystack = " ".join([
                    (ind.get("mesh_heading") or ""),
                    (ind.get("efo_term") or ""),
                ]).lower()
                return any(kw in haystack for kw in normalized_keywords)
            filtered = [ind for ind in indications if _matches(ind)]
            # Only apply the filter if it kept at least one row — see
            # docstring: cancer types ChEMBL doesn't tag would otherwise
            # silently zero out per-drug trials.
            if filtered:
                indications = filtered

    seen: set = set()
    out: List[str] = []
    for ind in indications:
        for ref in ind.get("indication_refs") or []:
            if (ref.get("ref_type") or "").lower() != "clinicaltrials":
                continue
            for nct in (ref.get("ref_id") or "").split(","):
                nct = nct.strip().upper()
                if nct.startswith("NCT") and nct not in seen:
                    seen.add(nct)
                    out.append(nct)
    return out


def fetch_pref_names(chembl_ids: List[str], batch_size: int = 50) -> Dict[str, str]:
    """
    Batch-resolve molecule_chembl_id → pref_name for a list of IDs. Used by
    /similar to replace IUPAC names from the local FAISS index with the
    recognizable ChEMBL preferred name (e.g. "ANASTROZOLE" instead of
    "2-[3-(2-cyanopropan-2-yl)-...nitrile"). Empty dict on ChEMBL failure.
    """
    if not chembl_ids or not CHEMBL_AVAILABLE or new_client is None:
        return {}

    out: Dict[str, str] = {}
    # Dedupe + filter out empties before the request.
    unique_ids = sorted({cid for cid in chembl_ids if cid})
    for i in range(0, len(unique_ids), batch_size):
        chunk = unique_ids[i:i + batch_size]
        try:
            results = _run_with_timeout(
                lambda ids=chunk: list(
                    new_client.molecule.filter(molecule_chembl_id__in=ids)
                    .only(["molecule_chembl_id", "pref_name"])
                )
            )
            for mol in results or []:
                cid = mol.get("molecule_chembl_id")
                pref = mol.get("pref_name")
                if cid and pref:
                    out[cid] = pref
        except FuturesTimeoutError:
            print(f"   ⚠️  pref_name batch timed out (chunk starting {i})")
        except Exception as e:
            print(f"   ⚠️  pref_name batch error: {e}")
    return out


def fetch_smiles(chembl_id: str) -> Optional[str]:
    """
    Cheap SMILES-only lookup for the similarity fallback. Always prefers the
    parent compound's SMILES — salt-form SMILES include the counterion
    (e.g. RIBOCICLIB SUCCINATE → "ribociclib.succinic_acid") which corrupts
    Morgan fingerprinting. Returns None if the drug can't be resolved or has
    no canonical SMILES anywhere up the hierarchy.
    """
    mol = _fetch_molecule_raw(chembl_id)
    if not mol:
        return None

    # Prefer parent SMILES when this is a salt/derivative.
    hierarchy = mol.get("molecule_hierarchy") or {}
    parent_id = hierarchy.get("parent_chembl_id")
    if parent_id and parent_id != chembl_id:
        parent = _fetch_molecule_raw(parent_id)
        parent_smiles = (parent.get("molecule_structures") or {}).get("canonical_smiles") if parent else None
        if parent_smiles:
            return parent_smiles

    # Otherwise, use the queried row's SMILES. If it's a multi-component salt
    # smiles (contains `.`), keep just the largest fragment so similarity runs
    # against the drug structure, not the counterion.
    structures = mol.get("molecule_structures") or {}
    smiles = structures.get("canonical_smiles")
    if smiles and "." in smiles:
        fragments = [f for f in smiles.split(".") if f]
        if fragments:
            smiles = max(fragments, key=len)
    return smiles


def fetch_drug_detail(chembl_id: str) -> Optional[Dict]:
    """
    Full drug-detail payload for the cancer research drug page. Returns None
    when the molecule cannot be resolved at all (ChEMBL down or unknown ID).
    """
    if not CHEMBL_AVAILABLE or new_client is None:
        return None

    mol = _fetch_molecule_raw(chembl_id)
    if not mol:
        return None

    hierarchy = mol.get("molecule_hierarchy") or {}
    parent_id = hierarchy.get("parent_chembl_id")
    parent_mol: Optional[Dict] = None
    if parent_id and parent_id != chembl_id:
        parent_mol = _fetch_molecule_raw(parent_id)

    # Prefer the parent's properties/synonyms (canonical) AND its SMILES.
    # Salt-form SMILES include the counterion (e.g. ".O=C(O)CCC(=O)O" for the
    # succinate) which corrupts both 2D-structure rendering and Morgan
    # fingerprint similarity. Fall back to the salt's largest fragment if the
    # parent has no structure.
    canonical = parent_mol or mol
    parent_structures = (parent_mol.get("molecule_structures") or {}) if parent_mol else {}
    salt_structures = mol.get("molecule_structures") or {}
    smiles = parent_structures.get("canonical_smiles") or salt_structures.get("canonical_smiles")
    if smiles and "." in smiles:
        fragments = [f for f in smiles.split(".") if f]
        if fragments:
            smiles = max(fragments, key=len)

    indications = _normalize_indications(_fetch_indications_raw(chembl_id))
    # If the queried row is a salt, also pull parent indications and merge —
    # ChEMBL files some indications under the parent only.
    if parent_id and parent_id != chembl_id:
        parent_indications = _normalize_indications(_fetch_indications_raw(parent_id))
        # Merge by mesh_heading only — _normalize_indications already collapses
        # the per-EFO-term rows ChEMBL returns into one row per MeSH heading,
        # so keying on (mesh, efo) here would re-split them when the salt's
        # winning EFO term differs from the parent's. Keep the metadata from
        # whichever side has the higher max_phase so the more clinically
        # advanced row's EFO mapping wins.
        merged: Dict[str, Dict] = {}
        for row in indications + parent_indications:
            key = (row.get("mesh_heading") or "").lower()
            if not key:
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(row)
                continue
            row_phase = row.get("max_phase") or 0
            existing_phase = existing.get("max_phase") or 0
            if row_phase > existing_phase:
                # Take the higher-phase row's metadata, sum refs from both.
                summed_refs = (existing.get("ref_count") or 0) + (row.get("ref_count") or 0)
                merged[key] = dict(row)
                merged[key]["ref_count"] = summed_refs
            else:
                existing["max_phase"] = max(existing_phase, row_phase)
                existing["ref_count"] = (existing.get("ref_count") or 0) + (row.get("ref_count") or 0)
        indications = sorted(
            merged.values(),
            key=lambda x: (
                -(x["max_phase"] or 0),
                -(x["ref_count"] or 0),
                (x["mesh_heading"] or "").lower(),
            ),
        )

    return {
        "chembl_id": chembl_id,
        "parent_chembl_id": parent_id if parent_id and parent_id != chembl_id else None,
        "pref_name": mol.get("pref_name"),
        "parent_pref_name": parent_mol.get("pref_name") if parent_mol else None,
        "molecule_type": mol.get("molecule_type") or canonical.get("molecule_type"),
        "max_phase": _coerce_int(canonical.get("max_phase")),
        "first_approval": _coerce_int(canonical.get("first_approval")),
        "smiles": smiles,
        "synonyms": _normalize_synonyms(canonical.get("molecule_synonyms") or []),
        "properties": _normalize_properties(canonical.get("molecule_properties")),
        "indications": indications,
    }


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) < 2:
        print("Usage: python chembl_drug_detail.py CHEMBL_ID")
        sys.exit(1)
    payload = fetch_drug_detail(sys.argv[1])
    print(json.dumps(payload, indent=2, default=str))
