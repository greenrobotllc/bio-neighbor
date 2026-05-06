"""
Cancer Research v2 — top-drugs aggregator.

Given a curated cancer subtype, build a ranked list of drugs by unioning:
  1. ChEMBL drug_indication API hits for the subtype's MeSH/EFO/curated terms
  2. Ligands already loaded for any cancer mechanism flagged in the subtype's
     parent cancer_type (cancer_mechanisms → mechanism_targets → ligands)
  3. The existing multi_api_disease_loader (openFDA/ClinicalTrials/PubChem)
     when a matching diseases row exists

Each drug is scored by ChEMBL `max_phase_for_ind` (clinical-stage weighted),
with source-count and trial-count as tiebreakers. Results are cached into
cancer_subtype_drugs; cache TTL is 30 days unless a manual refresh is requested.

Public API:
    aggregate_top_drugs_for_subtype(subtype_id, limit=25, refresh=False) -> Dict
    get_top_drugs_for_subtype(subtype_id, limit=25) -> List[Dict]
"""

import json
import math
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, List, Optional

from data_loader import DB_PATH

try:
    from chembl_webresource_client.new_client import new_client
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False
    new_client = None


CACHE_TTL_DAYS = 30
CHEMBL_QUERY_TIMEOUT = 30  # seconds, per indication-term query


# ---------------------------------------------------------------------------
# Subtype loading helpers
# ---------------------------------------------------------------------------


def _load_subtype(conn: sqlite3.Connection, subtype_id: int) -> Optional[Dict]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT cs.id, cs.name, cs.short_name, cs.mesh_id, cs.efo_id,
               cs.chembl_indication_terms, cs.cancer_type_id,
               ct.name AS type_name, ct.display_name AS type_display, ct.mesh_id AS type_mesh
        FROM cancer_subtypes cs
        JOIN cancer_types ct ON ct.id = cs.cancer_type_id
        WHERE cs.id = ?
        """,
        (subtype_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    indication_terms = []
    if row[5]:
        try:
            indication_terms = json.loads(row[5]) or []
        except (json.JSONDecodeError, TypeError):
            indication_terms = []

    return {
        "id": row[0],
        "name": row[1],
        "short_name": row[2],
        "mesh_id": row[3],
        "efo_id": row[4],
        "chembl_indication_terms": indication_terms,
        "cancer_type_id": row[6],
        "type_name": row[7],
        "type_display": row[8],
        "type_mesh": row[9],
    }


# ---------------------------------------------------------------------------
# ChEMBL drug_indication queries
# ---------------------------------------------------------------------------


def _chembl_query_with_timeout(query_fn, timeout: int = CHEMBL_QUERY_TIMEOUT):
    """Run a ChEMBL query in a worker thread with a hard timeout.

    The executor is *not* used as a context manager — `__exit__` calls
    `shutdown(wait=True)`, which blocks until the worker thread exits and
    silently nullifies the timeout. Using `shutdown(wait=False)` in a finally
    block releases the caller immediately on timeout; the orphaned worker
    finishes in the background.
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


def fetch_chembl_drugs_for_subtype(subtype: Dict, per_term_limit: int = 50) -> List[Dict]:
    """
    Query ChEMBL drug_indication for each curated indication term plus a fallback
    on the parent cancer's MeSH heading. De-duplicate by molecule_chembl_id,
    keeping the highest max_phase.

    Returns rows: {chembl_id, max_phase, mesh_heading, efo_term, mesh_id}.
    """
    if not CHEMBL_AVAILABLE or new_client is None:
        return []

    seen: Dict[str, Dict] = {}

    def absorb(items, fallback_phase: int = 0):
        """Accumulate ChEMBL drug_indication hits per chembl_id.

        Each call may add a new (mesh_heading, efo_term) match for an already-
        seen drug; we keep them all in `matches` so downstream ranking can
        boost drugs with multiple subtype-relevant filings instead of treating
        them as a single hit. Top-level mesh/efo metadata tracks the
        highest-phase match for back-compat with consumers that just want one
        evidence row per drug.
        """
        for item in items or []:
            chembl_id = item.get("molecule_chembl_id")
            if not chembl_id:
                continue
            # ChEMBL returns max_phase_for_ind as a string like '2.0' or '4.0'.
            phase = item.get("max_phase_for_ind")
            try:
                phase = int(float(phase)) if phase is not None else fallback_phase
            except (TypeError, ValueError):
                phase = fallback_phase
            match = {
                "max_phase": phase,
                "mesh_heading": item.get("mesh_heading"),
                "efo_term": item.get("efo_term"),
                "mesh_id": item.get("mesh_id"),
            }
            existing = seen.get(chembl_id)
            if existing is None:
                seen[chembl_id] = {
                    "chembl_id": chembl_id,
                    "max_phase": phase,
                    "mesh_heading": match["mesh_heading"],
                    "efo_term": match["efo_term"],
                    "mesh_id": match["mesh_id"],
                    "matches": [match],
                }
            else:
                existing["matches"].append(match)
                if phase > existing["max_phase"]:
                    # Promote the higher-phase match's metadata to the top
                    # level so back-compat consumers see the best filing.
                    existing["max_phase"] = phase
                    existing["mesh_heading"] = match["mesh_heading"]
                    existing["efo_term"] = match["efo_term"]
                    existing["mesh_id"] = match["mesh_id"]

    # Walk curated indication terms first — these are written by humans to
    # match real ChEMBL MeSH headings and are far more precise than the
    # parent cancer's MeSH heading. ChEMBL MeSH headings use spaces (e.g.
    # "Triple Negative Breast Neoplasms"), so we also try a hyphen↔space
    # normalized variant for each term to absorb both phrasings.
    for term in subtype.get("chembl_indication_terms") or []:
        if not term:
            continue
        variants = {term, term.replace("-", " "), term.replace("  ", " ").strip()}
        for variant in variants:
            try:
                results = _chembl_query_with_timeout(
                    lambda t=variant: list(
                        new_client.drug_indication.filter(mesh_heading__icontains=t)
                        .only(["molecule_chembl_id", "max_phase_for_ind", "mesh_heading", "efo_term", "mesh_id"])[:per_term_limit]
                    )
                )
                absorb(results)
                # Also try matching against efo_term in case the MeSH heading is too narrow.
                results_efo = _chembl_query_with_timeout(
                    lambda t=variant: list(
                        new_client.drug_indication.filter(efo_term__icontains=t)
                        .only(["molecule_chembl_id", "max_phase_for_ind", "mesh_heading", "efo_term", "mesh_id"])[:per_term_limit]
                    )
                )
                absorb(results_efo)
            except FuturesTimeoutError:
                print(f"   ⚠️  ChEMBL drug_indication timed out for term: {variant}")
            except Exception as e:
                print(f"   ⚠️  ChEMBL drug_indication error for '{variant}': {e}")

    # Pull by the subtype's OWN MeSH ID first. Subtype-specific filings (e.g.
    # "Triple Negative Breast Neoplasms") would otherwise be missed when the
    # subtype mesh_id is more specific than the curated indication terms.
    if subtype.get("mesh_id"):
        try:
            results = _chembl_query_with_timeout(
                lambda: list(
                    new_client.drug_indication.filter(mesh_id__exact=subtype["mesh_id"])
                    .only(["molecule_chembl_id", "max_phase_for_ind", "mesh_heading", "efo_term", "mesh_id"])[:per_term_limit * 2]
                )
            )
            absorb(results)
        except FuturesTimeoutError:
            print(f"   ⚠️  ChEMBL subtype-MeSH pull timed out for {subtype['mesh_id']}")
        except Exception as e:
            print(f"   ⚠️  ChEMBL subtype-MeSH error: {e}")

    # ALSO pull by parent cancer's MeSH ID (not just as fallback). Many drugs
    # — including subtype-specific ones like ribociclib for HR+ breast cancer —
    # are filed under the generic parent MeSH heading rather than a subtype
    # heading. Drugs that match both curated terms AND parent MeSH get a
    # higher source_count and naturally rank above parent-only matches.
    if subtype.get("type_mesh"):
        try:
            results = _chembl_query_with_timeout(
                lambda: list(
                    new_client.drug_indication.filter(mesh_id__exact=subtype["type_mesh"])
                    .only(["molecule_chembl_id", "max_phase_for_ind", "mesh_heading", "efo_term", "mesh_id"])[:per_term_limit * 2]
                )
            )
            absorb(results)
        except FuturesTimeoutError:
            print(f"   ⚠️  ChEMBL parent-MeSH pull timed out for {subtype['type_mesh']}")
        except Exception as e:
            print(f"   ⚠️  ChEMBL parent-MeSH error: {e}")

    # Compute a distinct-match count per drug — collapses identical hits from
    # multiple queries (e.g. mesh-id and efo-term variants of the same drug)
    # and exposes evidence multiplicity to ranking.
    out = []
    for row in seen.values():
        signatures = {
            (m.get("mesh_id"), m.get("efo_term"))
            for m in row.get("matches") or []
        }
        row["match_count"] = max(1, len(signatures))
        out.append(row)
    return out


def fetch_chembl_drug_names(chembl_ids: List[str], batch_size: int = 50) -> Dict[str, str]:
    """Resolve molecule_chembl_id → pref_name in batches."""
    names: Dict[str, str] = {}
    if not chembl_ids or not CHEMBL_AVAILABLE or new_client is None:
        return names

    for i in range(0, len(chembl_ids), batch_size):
        batch = chembl_ids[i:i + batch_size]
        try:
            results = _chembl_query_with_timeout(
                lambda ids=batch: list(
                    new_client.molecule.filter(molecule_chembl_id__in=ids)
                    .only(["molecule_chembl_id", "pref_name"])
                )
            )
            for mol in results or []:
                cid = mol.get("molecule_chembl_id")
                pref = mol.get("pref_name")
                if cid and pref:
                    names[cid] = pref
        except FuturesTimeoutError:
            print(f"   ⚠️  ChEMBL molecule name lookup timed out (batch starting {i})")
        except Exception as e:
            print(f"   ⚠️  ChEMBL molecule name lookup error: {e}")

    return names


# ---------------------------------------------------------------------------
# Local mechanism-ligand union
# ---------------------------------------------------------------------------


def fetch_mechanism_ligands_for_subtype(conn: sqlite3.Connection, subtype: Dict) -> List[Dict]:
    """
    Pull ligands attached to any mechanism that's flagged active in this
    subtype's parent cancer type. cancer_mechanisms.cancer_type is a free-text
    column, so we match by parent type_name OR type_display (case-insensitive).
    """
    cursor = conn.cursor()
    type_name = subtype.get("type_name") or ""
    type_display = subtype.get("type_display") or ""
    # Bidirectional substring match — see v2_subtype_mechanisms in api.py for
    # the rationale (free-text cancer_mechanisms.cancer_type column).
    cursor.execute(
        """
        SELECT DISTINCT l.id, l.name, l.chembl_id, l.molecule_index
        FROM cancer_mechanisms cm
        JOIN mechanism_targets mt ON mt.mechanism_id = cm.mechanism_id
        JOIN ligands l ON l.target_id = mt.target_id
        WHERE LOWER(cm.cancer_type) = LOWER(?)
           OR LOWER(cm.cancer_type) = LOWER(?)
           OR LOWER(cm.cancer_type) LIKE '%' || LOWER(?) || '%'
           OR LOWER(?) LIKE '%' || LOWER(cm.cancer_type) || '%'
        """,
        (type_name, type_display, type_display or type_name, type_name),
    )

    rows = []
    for r in cursor.fetchall():
        if not r[2]:  # require chembl_id for de-dup with ChEMBL pull
            continue
        rows.append({
            "ligand_id": r[0],
            "drug_name": r[1],
            "chembl_id": r[2],
            "molecule_index": r[3],
        })
    return rows


# ---------------------------------------------------------------------------
# Optional multi-API enrichment (best-effort)
# ---------------------------------------------------------------------------


def fetch_multi_api_drugs_for_subtype(subtype: Dict, limit: int = 25) -> List[Dict]:
    """
    Best-effort: query openFDA / ClinicalTrials / PubChem for the subtype name
    via multi_api_disease_loader. These rows usually do not carry a ChEMBL ID,
    so they only enrich `source_count` for drugs we already found via ChEMBL.
    """
    try:
        from multi_api_disease_loader import search_drugs_by_disease_multi_api
    except ImportError:
        return []

    try:
        return search_drugs_by_disease_multi_api(subtype["name"], max_drugs=limit) or []
    except Exception as e:
        print(f"   ⚠️  multi_api_disease_loader error: {e}")
        return []


# ---------------------------------------------------------------------------
# Aggregation + scoring
# ---------------------------------------------------------------------------


def _compute_rank_score(max_phase: int, source_count: int, trial_count: Optional[int]) -> float:
    """max_phase * 100 + source_count * 10 + log10(trial_count + 1) * 5."""
    score = float(max(0, max_phase)) * 100.0
    score += float(max(1, source_count)) * 10.0
    if trial_count and trial_count > 0:
        score += math.log10(trial_count + 1) * 5.0
    return score


def aggregate_top_drugs_for_subtype(
    subtype_id: int,
    limit: int = 25,
    refresh: bool = False,
) -> Dict:
    """
    Build the ranked drug list, persist into cancer_subtype_drugs, and return a
    summary dict with counts + the cached rows. Honors the 30-day cache unless
    `refresh=True`.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        subtype = _load_subtype(conn, subtype_id)
        if not subtype:
            return {"success": False, "error": f"Subtype {subtype_id} not found"}

        if not refresh and not _cache_is_stale(conn, subtype_id):
            cached = get_top_drugs_for_subtype(subtype_id, limit=limit, conn=conn)
            # `len(cached)` would equal `limit` whenever more rows exist, hiding
            # the true cache size from the UI. Read the row count directly so
            # the response matches the refresh path.
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM cancer_subtype_drugs WHERE subtype_id = ?",
                (subtype_id,),
            )
            total = cursor.fetchone()[0]
            return {
                "success": True,
                "subtype_id": subtype_id,
                "from_cache": True,
                "drug_count": total,
                "drugs": cached,
            }

        # 1. ChEMBL drug_indication
        t0 = time.time()
        chembl_rows = fetch_chembl_drugs_for_subtype(subtype)
        print(f"   ChEMBL drug_indication returned {len(chembl_rows)} rows in {time.time()-t0:.1f}s")

        chembl_ids = [r["chembl_id"] for r in chembl_rows]
        names_map = fetch_chembl_drug_names(chembl_ids) if chembl_ids else {}

        # 2. Local mechanism-ligand union
        mech_rows = fetch_mechanism_ligands_for_subtype(conn, subtype)
        print(f"   cancer_mechanisms join returned {len(mech_rows)} ligands")

        # 3. Best-effort multi-API enrichment (only by name → source_count bump)
        multi_rows = fetch_multi_api_drugs_for_subtype(subtype, limit=max(limit, 25))

        # Merge by chembl_id (primary key). multi_api rows merge by drug_name.
        merged: Dict[str, Dict] = {}

        for r in chembl_rows:
            cid = r["chembl_id"]
            merged[cid] = {
                "chembl_id": cid,
                "drug_name": names_map.get(cid) or cid,
                "max_phase": r.get("max_phase") or 0,
                "sources": {"chembl_indication"},
                "evidence": {
                    "mesh_heading": r.get("mesh_heading"),
                    "efo_term": r.get("efo_term"),
                    "mesh_id": r.get("mesh_id"),
                },
                # Carries through into rank_score so drugs with multiple
                # subtype-relevant ChEMBL filings outrank single-hit drugs.
                "chembl_match_count": r.get("match_count", 1),
                "ligand_id": None,
                "molecule_index": None,
            }

        for r in mech_rows:
            cid = r["chembl_id"]
            if cid in merged:
                merged[cid]["sources"].add("cancer_mechanism")
                # ChEMBL seed pre-fills these as None; setdefault would lock that
                # in. Only overwrite when the mechanism row actually has a value.
                if r.get("ligand_id") is not None:
                    merged[cid]["ligand_id"] = r["ligand_id"]
                if r.get("molecule_index") is not None:
                    merged[cid]["molecule_index"] = r["molecule_index"]
                if not merged[cid]["drug_name"] or merged[cid]["drug_name"] == cid:
                    merged[cid]["drug_name"] = r.get("drug_name") or merged[cid]["drug_name"]
            else:
                merged[cid] = {
                    "chembl_id": cid,
                    "drug_name": r.get("drug_name") or cid,
                    "max_phase": 0,
                    "sources": {"cancer_mechanism"},
                    "evidence": {"source": "cancer_mechanism"},
                    "chembl_match_count": 0,  # no chembl_indication hit
                    "ligand_id": r.get("ligand_id"),
                    "molecule_index": r.get("molecule_index"),
                }

        # multi_api rows usually lack chembl_id; match by drug name to bump source_count.
        name_index = {(v["drug_name"] or "").lower(): k for k, v in merged.items()}
        for r in multi_rows:
            drug_name = (r.get("name") or r.get("generic_name") or "").strip()
            if not drug_name:
                continue
            cid_match = name_index.get(drug_name.lower())
            if cid_match:
                merged[cid_match]["sources"].add(f"multi_api:{r.get('api_source','unknown')}")

        # Backfill molecule_index from local DB for chembl-only rows.
        try:
            from molecule_utils import find_molecule_by_chembl_id
            for cid, row in merged.items():
                if row["molecule_index"] is None:
                    idx = find_molecule_by_chembl_id(cid, conn)
                    if idx is not None:
                        row["molecule_index"] = idx
        except ImportError:
            pass

        # Score and persist
        rows_to_persist = []
        for row in merged.values():
            # Effective source_count = distinct data systems (sources set) +
            # bounded boost for ChEMBL evidence multiplicity. The cap stops a
            # drug with many parent-MeSH filings from out-ranking a drug with
            # a single Phase 4 entry.
            chembl_boost = min(max(row.get("chembl_match_count", 1) - 1, 0), 3)
            source_count = len(row["sources"]) + chembl_boost
            primary_source = (
                "chembl_indication" if "chembl_indication" in row["sources"]
                else "cancer_mechanism" if "cancer_mechanism" in row["sources"]
                else next(iter(row["sources"]))
            )
            rank_score = _compute_rank_score(row["max_phase"], source_count, None)
            rows_to_persist.append({
                **row,
                "source_count": source_count,
                "primary_source": primary_source,
                "rank_score": rank_score,
            })

        rows_to_persist.sort(key=lambda r: r["rank_score"], reverse=True)
        _replace_subtype_cache(conn, subtype_id, rows_to_persist)

        cached = get_top_drugs_for_subtype(subtype_id, limit=limit, conn=conn)
        return {
            "success": True,
            "subtype_id": subtype_id,
            "from_cache": False,
            "chembl_count": len(chembl_rows),
            "mechanism_count": len(mech_rows),
            "multi_api_count": len(multi_rows),
            "drug_count": len(rows_to_persist),
            "drugs": cached,
        }
    finally:
        conn.close()


def _cache_is_stale(conn: sqlite3.Connection, subtype_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*),
               MIN(julianday('now') - julianday(cached_at)) AS oldest_days
        FROM cancer_subtype_drugs
        WHERE subtype_id = ?
        """,
        (subtype_id,),
    )
    count, oldest_days = cursor.fetchone()
    if not count:
        return True
    if oldest_days is None:
        return True
    return oldest_days > CACHE_TTL_DAYS


def _replace_subtype_cache(conn: sqlite3.Connection, subtype_id: int, rows: List[Dict]) -> None:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cancer_subtype_drugs WHERE subtype_id = ?", (subtype_id,))
    for row in rows:
        cursor.execute(
            """
            INSERT INTO cancer_subtype_drugs (
                subtype_id, drug_id, ligand_id, molecule_index,
                chembl_id, drug_name, max_phase, source, source_count,
                trial_count, rank_score, evidence, cached_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                subtype_id,
                None,
                row.get("ligand_id"),
                row.get("molecule_index"),
                row["chembl_id"],
                row.get("drug_name") or row["chembl_id"],
                row.get("max_phase") or 0,
                row.get("primary_source") or "unknown",
                row.get("source_count") or 1,
                None,
                row.get("rank_score") or 0.0,
                json.dumps(row.get("evidence") or {}),
            ),
        )
    conn.commit()


def get_top_drugs_for_subtype(
    subtype_id: int,
    limit: int = 25,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict]:
    """Read cached rows for a subtype, sorted by rank_score desc."""
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, subtype_id, drug_id, ligand_id, molecule_index,
                   chembl_id, drug_name, max_phase, source, source_count,
                   trial_count, rank_score, evidence, cached_at
            FROM cancer_subtype_drugs
            WHERE subtype_id = ?
            ORDER BY rank_score DESC, drug_name ASC
            LIMIT ?
            """,
            (subtype_id, limit),
        )
        rows = cursor.fetchall()
    finally:
        if own_conn:
            conn.close()

    drugs = []
    for r in rows:
        evidence = {}
        if r[12]:
            try:
                evidence = json.loads(r[12]) or {}
            except (json.JSONDecodeError, TypeError):
                evidence = {}
        drugs.append({
            "id": r[0],
            "subtype_id": r[1],
            "drug_id": r[2],
            "ligand_id": r[3],
            "molecule_index": r[4],
            "chembl_id": r[5],
            "drug_name": r[6],
            "max_phase": r[7],
            "source": r[8],
            "source_count": r[9],
            "trial_count": r[10],
            "rank_score": r[11],
            "evidence": evidence,
            "cached_at": r[13],
        })
    return drugs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aggregate top drugs for a cancer subtype")
    parser.add_argument("subtype_id", type=int, help="ID of the cancer_subtypes row")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    result = aggregate_top_drugs_for_subtype(args.subtype_id, limit=args.limit, refresh=args.refresh)
    print(json.dumps(result, indent=2, default=str))
