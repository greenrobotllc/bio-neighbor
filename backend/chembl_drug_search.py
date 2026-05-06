"""
Live ChEMBL drug-name search with write-through caching.

Used by /search/drugs to extend the local drugs-table search with live ChEMBL
hits. Any ChEMBL hit that isn't already in the local drugs table is inserted
on-the-fly so the next search for the same drug is a fast local hit.
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, List, Optional, Set

from data_loader import DB_PATH

try:
    from chembl_webresource_client.new_client import new_client
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False
    new_client = None


CHEMBL_SEARCH_TIMEOUT = 5  # seconds — kept tight so type-ahead stays responsive


def _run_with_timeout(query_fn, timeout: int = CHEMBL_SEARCH_TIMEOUT):
    """Run a ChEMBL query in a worker thread with a hard timeout.

    See chembl_drug_detail._run_with_timeout for why we avoid `with` here:
    the context manager calls `shutdown(wait=True)` which blocks on the worker
    thread even after the future times out, making the timeout itself useless.
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


def search_chembl_by_name(query: str, limit: int = 20) -> List[Dict]:
    """
    Search ChEMBL by molecule pref_name. Returns simplified rows ready to
    merge with local drugs-table results. Empty list on timeout / network
    failure / ChEMBL unavailable — never raises.
    """
    if not query or not CHEMBL_AVAILABLE or new_client is None:
        return []

    try:
        rows = _run_with_timeout(
            lambda: list(
                new_client.molecule.filter(pref_name__icontains=query)
                .only(["molecule_chembl_id", "pref_name", "max_phase", "molecule_type"])[:limit]
            )
        )
    except FuturesTimeoutError:
        print(f"   ⚠️  ChEMBL drug-name search timed out for '{query}'")
        return []
    except Exception as e:
        print(f"   ⚠️  ChEMBL drug-name search error for '{query}': {e}")
        return []

    out: List[Dict] = []
    for r in rows or []:
        chembl_id = r.get("molecule_chembl_id")
        pref_name = r.get("pref_name")
        if not chembl_id or not pref_name:
            continue
        max_phase = r.get("max_phase")
        try:
            max_phase = int(float(max_phase)) if max_phase is not None else None
        except (TypeError, ValueError):
            max_phase = None
        out.append({
            "chembl_id": chembl_id,
            "name": pref_name,
            "max_phase": max_phase,
            "molecule_type": r.get("molecule_type"),
        })
    return out


def upsert_chembl_hits_into_drugs(
    hits: List[Dict],
    conn: Optional[sqlite3.Connection] = None,
) -> List[int]:
    """
    Write-through cache: for any ChEMBL hit that doesn't already have a row in
    `drugs` (matched by chembl_id), insert one. Returns the list of newly-
    inserted drug IDs (in input order; rows that were already cached get None).
    """
    if not hits:
        return []
    # When the caller passes their own `conn`, they own the transaction —
    # don't commit, rollback, or close it from here. Only manage lifecycle for
    # the connection we open ourselves.
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        # Find which chembl_ids already exist locally.
        chembl_ids = [h["chembl_id"] for h in hits if h.get("chembl_id")]
        existing: Set[str] = set()
        if chembl_ids:
            placeholders = ",".join(["?"] * len(chembl_ids))
            cursor.execute(
                f"SELECT chembl_id FROM drugs WHERE chembl_id IN ({placeholders})",
                chembl_ids,
            )
            existing = {row[0] for row in cursor.fetchall() if row[0]}

        new_ids: List[Optional[int]] = []
        for hit in hits:
            cid = hit.get("chembl_id")
            if not cid or cid in existing:
                new_ids.append(None)
                continue
            description_parts = []
            if hit.get("max_phase") is not None:
                description_parts.append(f"ChEMBL max_phase={hit['max_phase']}")
            if hit.get("molecule_type"):
                description_parts.append(hit["molecule_type"])
            description = "; ".join(description_parts) or None
            # Atomic insert-if-absent: the SELECT-then-INSERT preflight above
            # is racy under concurrent requests for the same chembl_id (Flask
            # is multi-threaded). Pushing the existence check into the INSERT
            # statement closes the window. If another writer beat us, rowcount
            # will be 0 and we look up the existing id below.
            cursor.execute(
                """
                INSERT INTO drugs (name, generic_name, chembl_id, description)
                SELECT ?, ?, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM drugs WHERE chembl_id = ?)
                """,
                (hit["name"], hit["name"], cid, description, cid),
            )
            if cursor.rowcount == 1:
                new_ids.append(cursor.lastrowid)
            else:
                new_ids.append(None)
            existing.add(cid)

        if own_conn:
            conn.commit()
        return new_ids
    finally:
        if own_conn:
            conn.close()


def _relevance_score(query: str, name: str) -> int:
    """Rank: exact = 0, starts-with = 1, contains = 2, other = 3 (lower better)."""
    q = (query or "").lower()
    n = (name or "").lower()
    if not q or not n:
        return 99
    if n == q:
        return 0
    if n.startswith(q):
        return 1
    if q in n:
        return 2
    return 3


def merge_drug_search_results(
    local_results: List[Dict],
    chembl_hits: List[Dict],
    chembl_id_to_local_id: Dict[str, int],
    query: str,
    limit: int,
) -> List[Dict]:
    """
    Merge local drugs-table rows with ChEMBL hits. Dedupe by chembl_id when
    available, otherwise by lowercased name. Annotate each row with `source`:
        - "local"  — already in drugs table
        - "chembl" — fetched from ChEMBL on-demand (now also cached)
    """
    by_key: Dict[str, Dict] = {}

    def upsert(row: Dict, source: str):
        key = (row.get("chembl_id") or row.get("name", "")).lower()
        if not key:
            return
        if key not in by_key:
            row = dict(row)
            row["source"] = source
            by_key[key] = row
        else:
            # Local entry takes precedence for ID/details; just upgrade source
            # if both sources had it (means it was cached during this search).
            existing = by_key[key]
            if existing["source"] == "chembl" and source == "local":
                # Keep more complete local row.
                row = dict(row)
                row["source"] = "local"
                by_key[key] = row

    for row in local_results:
        upsert(row, "local")

    for hit in chembl_hits:
        cid = hit.get("chembl_id")
        # If we just inserted this ChEMBL hit into drugs, it now has a local id
        # — present it as "chembl" source so the UI labels it as freshly-fetched
        # in this search, but include the new id for navigation.
        local_id = chembl_id_to_local_id.get(cid) if cid else None
        merged_row = {
            "id": local_id,
            "name": hit.get("name"),
            "generic_name": hit.get("name"),
            "brand_names": [],
            "chembl_id": cid,
            "max_phase": hit.get("max_phase"),
        }
        upsert(merged_row, "chembl")

    rows = list(by_key.values())
    rows.sort(key=lambda r: (_relevance_score(query, r.get("name") or ""), (r.get("name") or "").lower()))
    return rows[:limit]
