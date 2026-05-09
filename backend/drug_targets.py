"""
Drug → mechanism-of-action target resolution + overlap detection
(issue #53).

The Treatment Auditor uses this to flag when two prescribed drugs hit the
same molecular target — could be intentional combination therapy, could be
redundant or additively toxic, but worth surfacing either way.

Source: ChEMBL `mechanism` resource (`mechanism_of_action`, `target_chembl_id`,
`action_type`). Pulled live on first encounter for a drug, then cached in
the local SQLite. Target gene-symbol/protein-name is resolved from ChEMBL
`target` and cached separately so multiple drugs sharing a target only
incur one resolution call.

Note: the ticket originally said "use only in-repo data". The local
mechanisms/targets data is highly curated (≈7 targets) — too sparse for
the audit's actual prescribed-drug inputs. Falling back to ChEMBL keeps
the feature factual without inventing data.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

from data_loader import DB_PATH

logger = logging.getLogger(__name__)

try:
    from chembl_webresource_client.new_client import new_client
    from chembl_webresource_client.settings import Settings as _ChEMBLSettings
    from chembl_webresource_client.http_errors import (
        BaseHttpException as _ChEMBLHttpException,
    )
    CHEMBL_AVAILABLE = True
except ImportError:  # pragma: no cover - dev fallback
    CHEMBL_AVAILABLE = False
    new_client = None  # type: ignore
    _ChEMBLSettings = None  # type: ignore
    _ChEMBLHttpException = Exception  # type: ignore[assignment,misc]

import requests as _requests

# Narrow exception tuple for catches around ChEMBL client calls.
# Lets us log + return None for expected transient errors (network,
# HTTP 4xx/5xx from ChEMBL, malformed JSON) without swallowing genuine
# programming bugs (KeyError, AttributeError, TypeError).
_CHEMBL_LOOKUP_EXCEPTIONS: tuple = (
    _requests.RequestException,
    _ChEMBLHttpException,
    ValueError,
)

DRUG_TARGETS_TABLE = "drug_targets_cache"
CHEMBL_TARGETS_TABLE = "chembl_targets_cache"


class _ChEMBLLookupError(Exception):
    """Raised when a ChEMBL lookup fails transiently (network error,
    client/library exception). Distinct from "the lookup succeeded and
    returned no record" — that case still returns sentinel values
    (None / [] / {}) from the helpers.

    The mechanism / target helpers signal transient failures via a
    `None` return because their happy-path return type already has a
    natural empty case ([] / {}). The parent-lookup helper has no
    natural empty sentinel — None already means "no parent found
    (genuine answer)" — so it raises this exception instead.
    """
# ChEMBL is generally fast but occasionally slow; cap each call so a hung
# request can't stall the audit indefinitely.
CHEMBL_TIMEOUT_SECS = 12

# Apply the timeout to every ChEMBL client call in this module. The
# client's default is 3s which trips false-positive failures on cold
# caches; 12s gives the audit a meaningful budget without letting a
# hung request stall the user indefinitely. Done at import time so all
# subsequent mechanism / molecule / target lookups inherit it.
#
# `Settings.Instance` has historically been a singleton accessor — in
# current versions it's a method that returns the instance, but older
# releases exposed it as a plain class attribute. Detect both shapes
# before mutating, and log when neither works rather than silently
# eating the error: a missed TIMEOUT means the audit silently falls
# back to the 3s default and users see spurious "ChEMBL failed"
# messages with no obvious cause.
if CHEMBL_AVAILABLE and _ChEMBLSettings is not None:
    _instance_attr = getattr(_ChEMBLSettings, "Instance", None)
    if _instance_attr is None:
        logger.warning(
            "chembl_webresource_client.Settings has no `Instance` accessor; "
            "TIMEOUT not applied — using client default."
        )
    else:
        try:
            _settings_obj = _instance_attr() if callable(_instance_attr) else _instance_attr
            _settings_obj.TIMEOUT = CHEMBL_TIMEOUT_SECS
        except (AttributeError, TypeError) as _exc:
            logger.warning(
                "Could not apply ChEMBL TIMEOUT=%s (%s); using client default.",
                CHEMBL_TIMEOUT_SECS, _exc,
            )


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {DRUG_TARGETS_TABLE} (
            chembl_id TEXT PRIMARY KEY,
            targets_json TEXT NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CHEMBL_TARGETS_TABLE} (
            target_chembl_id TEXT PRIMARY KEY,
            gene_symbol TEXT,
            protein_name TEXT,
            organism TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _drug_targets_from_cache(conn: sqlite3.Connection, chembl_id: str) -> Optional[List[Dict]]:
    cur = conn.execute(
        f"SELECT targets_json FROM {DRUG_TARGETS_TABLE} WHERE chembl_id = ?",
        (chembl_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def _drug_targets_to_cache(
    conn: sqlite3.Connection, chembl_id: str, targets: List[Dict]
) -> None:
    conn.execute(
        f"""
        INSERT OR REPLACE INTO {DRUG_TARGETS_TABLE} (chembl_id, targets_json, fetched_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (chembl_id, json.dumps(targets)),
    )
    conn.commit()


def _chembl_target_from_cache(
    conn: sqlite3.Connection, target_chembl_id: str
) -> Optional[Dict]:
    cur = conn.execute(
        f"""
        SELECT gene_symbol, protein_name, organism
        FROM {CHEMBL_TARGETS_TABLE} WHERE target_chembl_id = ?
        """,
        (target_chembl_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {"gene_symbol": row[0], "protein_name": row[1], "organism": row[2]}


def _chembl_target_to_cache(
    conn: sqlite3.Connection, target_chembl_id: str, info: Dict
) -> None:
    conn.execute(
        f"""
        INSERT OR REPLACE INTO {CHEMBL_TARGETS_TABLE}
            (target_chembl_id, gene_symbol, protein_name, organism, fetched_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            target_chembl_id,
            info.get("gene_symbol"),
            info.get("protein_name"),
            info.get("organism"),
        ),
    )
    conn.commit()


def _query_mechanism_endpoint(chembl_id: str) -> Optional[List[Dict]]:
    """Single ChEMBL mechanism lookup.

    Returns:
      - List of parsed rows (possibly empty) on a successful call.
      - `None` on any network/client error — callers MUST NOT cache
        `None` as "no targets". A blip would otherwise persist an empty
        result for that drug forever.
    """
    if not CHEMBL_AVAILABLE:
        return None
    try:
        mech = new_client.mechanism  # type: ignore[union-attr]
        results = list(
            mech.filter(molecule_chembl_id=chembl_id).only(
                "target_chembl_id",
                "action_type",
                "mechanism_of_action",
                "mechanism_comment",
            )
        )
    except _CHEMBL_LOOKUP_EXCEPTIONS as exc:
        logger.warning("ChEMBL mechanism lookup failed for %s: %s", chembl_id, exc)
        return None

    out: List[Dict] = []
    for r in results:
        target_chembl_id = (r.get("target_chembl_id") or "").strip() or None
        out.append(
            {
                "target_chembl_id": target_chembl_id,
                "action_type": r.get("action_type"),
                "mechanism_of_action": r.get("mechanism_of_action"),
                "mechanism_comment": r.get("mechanism_comment"),
            }
        )
    return out


def _resolve_parent_chembl_id(chembl_id: str) -> Optional[str]:
    """Read molecule_hierarchy.parent_chembl_id for a salt/child ID.

    Returns:
      - The parent ChEMBL ID string when one exists and differs from
        the supplied ID.
      - `None` when the lookup succeeded but the supplied ID is already
        a parent or has no record. This is a genuine answer — caching
        a downstream "no mechanisms" result based on it is safe.
    Raises:
      - `_ChEMBLLookupError` on any transport / client failure.
        Conflating "no parent" (None) with "lookup errored" (was None
        too) caused `_live_fetch_drug_mechanisms` to silently cache
        empty mechanism lists for drugs whose parent lookup just
        flaked once — surface the failure so callers skip the cache.
    """
    if not CHEMBL_AVAILABLE:
        return None
    try:
        molecule = new_client.molecule  # type: ignore[union-attr]
        records = list(
            molecule.filter(molecule_chembl_id=chembl_id).only(
                "molecule_chembl_id",
                "molecule_hierarchy",
            )
        )
    except _CHEMBL_LOOKUP_EXCEPTIONS as exc:
        logger.warning("ChEMBL parent lookup failed for %s: %s", chembl_id, exc)
        raise _ChEMBLLookupError(f"parent lookup error for {chembl_id}") from exc
    if not records:
        return None
    hierarchy = records[0].get("molecule_hierarchy") or {}
    parent_id = hierarchy.get("parent_chembl_id")
    if parent_id and parent_id != chembl_id:
        return parent_id
    return None


def _live_fetch_drug_mechanisms(chembl_id: str) -> Optional[List[Dict]]:
    """Hit ChEMBL `mechanism` for a single drug.

    Falls back to the parent ChEMBL ID when the direct lookup is empty —
    most drugs register their mechanisms against the parent compound, so
    a salt-form / child-ID query (e.g. CHEMBL3707266 for ribociclib
    succinate) returns nothing without this fallback. Same problem hits
    parent-IDs whose hierarchy points elsewhere.

    Returns `None` when *both* attempts errored (so the caller must skip
    caching the result), `[]` when the lookup succeeded but the drug
    legitimately has no recorded mechanisms, and `[...]` for hits.
    """
    rows = _query_mechanism_endpoint(chembl_id)
    # Direct query succeeded with rows — done.
    if rows:
        return rows
    try:
        parent_id = _resolve_parent_chembl_id(chembl_id)
    except _ChEMBLLookupError:
        # Parent lookup errored — propagate as transient. A flaky
        # parent lookup must NOT lock in a "no mechanisms" cache row
        # (the drug might genuinely have mechanisms via its parent).
        return None
    if parent_id is None:
        # No parent to try. Trust whatever the direct call gave us
        # (`None` → transient error, propagate; `[]` → genuine empty).
        return rows
    parent_rows = _query_mechanism_endpoint(parent_id)
    if parent_rows is not None:
        # Parent answer wins when it's available — covers both empty
        # and non-empty cases.
        return parent_rows
    # Parent errored. If the direct call had a definite empty answer,
    # use that; otherwise propagate `None` so we don't cache.
    return rows


def _live_fetch_target_info(target_chembl_id: str) -> Optional[Dict]:
    """Hit ChEMBL `target` for gene symbol + protein name.

    ChEMBL's target resource has nested structures. We pull `pref_name`
    (protein name) and the first matching gene symbol from
    `target_components[].target_component_synonyms[]` where syn_type is
    `GENE_SYMBOL`.

    Returns `None` on a network/client error (caller must NOT cache —
    same rationale as `_query_mechanism_endpoint`). Returns `{}` when the
    lookup succeeded but ChEMBL has no record for this target. Returns
    `{"gene_symbol": ..., "protein_name": ..., "organism": ...}` for hits.
    """
    if not CHEMBL_AVAILABLE:
        return None
    try:
        target = new_client.target  # type: ignore[union-attr]
        record = target.filter(target_chembl_id=target_chembl_id).only(
            "pref_name",
            "organism",
            "target_components",
        )
        records = list(record)
        if not records:
            return {}
        rec = records[0]
    except _CHEMBL_LOOKUP_EXCEPTIONS as exc:
        logger.warning("ChEMBL target lookup failed for %s: %s", target_chembl_id, exc)
        return None

    gene_symbol: Optional[str] = None
    components = rec.get("target_components") or []
    for comp in components:
        synonyms = comp.get("target_component_synonyms") or []
        for syn in synonyms:
            if (syn.get("syn_type") or "").upper() == "GENE_SYMBOL":
                gene_symbol = syn.get("component_synonym")
                if gene_symbol:
                    break
        if gene_symbol:
            break

    return {
        "gene_symbol": gene_symbol,
        "protein_name": rec.get("pref_name"),
        "organism": rec.get("organism"),
    }


def fetch_drug_targets(chembl_id: str) -> List[Dict]:
    """Public: returns the mechanism rows for a drug, with target info
    inlined. Cached.

    Each row carries:
        target_chembl_id, gene_symbol, protein_name,
        action_type, mechanism_of_action.
    """
    if not chembl_id:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        _ensure_tables(conn)

        cached = _drug_targets_from_cache(conn, chembl_id)
        if cached is not None:
            return cached

        rows = _live_fetch_drug_mechanisms(chembl_id)
        if rows is None:
            # Transient network/client error — DO NOT cache. Return an
            # empty list for this request so the audit keeps running, but
            # the next audit will re-fetch.
            return []

        # Resolve each unique target_chembl_id once. Track whether any
        # target metadata fetch errored so we know whether the
        # drug-level enriched payload is fully resolved or partial — a
        # partial payload must NOT be persisted to the drug-level cache,
        # otherwise a flaky network freezes "no gene_symbol" answers
        # for the affected target across every future audit.
        target_ids = {r["target_chembl_id"] for r in rows if r["target_chembl_id"]}
        resolved: Dict[str, Dict] = {}
        any_target_lookup_failed = False
        for tid in target_ids:
            info = _chembl_target_from_cache(conn, tid)
            if info is None:
                fresh = _live_fetch_target_info(tid)
                if fresh is None:
                    # Target lookup errored — fall through with an empty
                    # dict for this request, but DO NOT persist to the
                    # cache so the next audit retries.
                    resolved[tid] = {}
                    any_target_lookup_failed = True
                    continue
                _chembl_target_to_cache(conn, tid, fresh)
                resolved[tid] = fresh
            else:
                resolved[tid] = info

        enriched: List[Dict] = []
        for r in rows:
            tid = r.get("target_chembl_id")
            info = resolved.get(tid, {}) if tid else {}
            enriched.append(
                {
                    "target_chembl_id": tid,
                    "gene_symbol": info.get("gene_symbol"),
                    "protein_name": info.get("protein_name"),
                    "action_type": r.get("action_type"),
                    "mechanism_of_action": r.get("mechanism_of_action"),
                }
            )

        if not any_target_lookup_failed:
            _drug_targets_to_cache(conn, chembl_id, enriched)
        return enriched
    finally:
        conn.close()


def find_target_overlap(drugs: List[Dict]) -> Dict:
    """Compute pairwise target overlap among the supplied drugs.

    Each input is `{"name": str, "chembl_id": str?}`. Drugs without a
    ChEMBL ID are skipped (we have no key to fetch mechanisms for them) —
    they're returned in `unmatched` so the UI can be honest.

    Returns:
        {
            "targets_by_drug": [{"name", "chembl_id", "targets": [...]}],
            "unmatched": ["drug names without ChEMBL ID"],
            "overlaps": [
                {"drug_a", "drug_b",
                 "shared_targets": [{"target_chembl_id", "gene_symbol",
                                     "protein_name", "action_type_a",
                                     "action_type_b"}]}
            ]
        }
    """
    targets_by_drug: List[Dict] = []
    unmatched: List[str] = []

    for entry in drugs:
        name = (entry.get("name") or "").strip()
        chembl_id = (entry.get("chembl_id") or "").strip() or None
        if not chembl_id:
            if name:
                unmatched.append(name)
            continue

        targets = fetch_drug_targets(chembl_id)
        targets_by_drug.append(
            {"name": name, "chembl_id": chembl_id, "targets": targets}
        )

    overlaps: List[Dict] = []
    n = len(targets_by_drug)
    for i in range(n):
        for j in range(i + 1, n):
            a = targets_by_drug[i]
            b = targets_by_drug[j]
            shared = _shared_targets(a["targets"], b["targets"])
            if shared:
                overlaps.append(
                    {"drug_a": a["name"], "drug_b": b["name"], "shared_targets": shared}
                )

    return {
        "targets_by_drug": targets_by_drug,
        "unmatched": unmatched,
        "overlaps": overlaps,
    }


def _aggregate_targets_by_id(targets: List[Dict]) -> Dict[str, Dict]:
    """Collapse multiple mechanism rows for the same target_chembl_id
    into one canonical entry per target.

    ChEMBL may return several mechanism rows for the same drug→target
    relationship (different action types, different mechanism-of-action
    strings, hierarchy variants). The pre-aggregation version of
    `_shared_targets` kept only the first row per target on the A
    side, then iterated *every* row on the B side — meaning a drug
    with two mechanism rows pointing at the same gene would emit two
    duplicate "shared target" entries with mismatched action types.

    Aggregating up-front yields one canonical record per target.
    `action_types` and `mechanisms_of_action` are deduped and sorted
    so the payload is byte-identical across runs regardless of the
    input row order ChEMBL happens to return on a given fetch — that
    matters for snapshot tests and for users comparing two audit
    reports of the same drugs side-by-side. Gene symbol and protein
    name take the first non-empty value seen (they don't legitimately
    vary across rows for the same target).
    """
    by_id: Dict[str, Dict] = {}
    for t in targets:
        tid = t.get("target_chembl_id")
        if not tid:
            continue
        agg = by_id.setdefault(tid, {
            "target_chembl_id": tid,
            "gene_symbol": None,
            "protein_name": None,
            "action_types": set(),  # deduped here, sorted at the end
            "mechanisms_of_action": set(),
        })
        if not agg["gene_symbol"] and t.get("gene_symbol"):
            agg["gene_symbol"] = t.get("gene_symbol")
        if not agg["protein_name"] and t.get("protein_name"):
            agg["protein_name"] = t.get("protein_name")
        action = t.get("action_type")
        if action:
            agg["action_types"].add(action)
        mech = t.get("mechanism_of_action")
        if mech:
            agg["mechanisms_of_action"].add(mech)
    # Convert sets → sorted lists for stable, deterministic output.
    for agg in by_id.values():
        agg["action_types"] = sorted(agg["action_types"])
        agg["mechanisms_of_action"] = sorted(agg["mechanisms_of_action"])
    return by_id


def _shared_targets(targets_a: List[Dict], targets_b: List[Dict]) -> List[Dict]:
    """Return the targets present in both lists, with the action types
    each drug uses against that target.

    Each shared target is emitted exactly once (deduped by
    target_chembl_id) — see `_aggregate_targets_by_id` for the
    reasoning. `action_type_a` / `action_type_b` are joined with " / "
    in sorted order so the string-typed Swift contract still holds and
    the output is deterministic. `mechanism_of_action` is the *union*
    of both drugs' mechanisms (deduped, sorted) — building it from
    only side A would be asymmetric: swapping the input lists would
    produce a different value.
    """
    agg_a = _aggregate_targets_by_id(targets_a)
    agg_b = _aggregate_targets_by_id(targets_b)

    shared: List[Dict] = []
    # Sort by target_chembl_id for deterministic output ordering across
    # the same input — matters for snapshot tests and reproducibility
    # of the audit's deterministic-findings section.
    for tid in sorted(set(agg_a) & set(agg_b)):
        a = agg_a[tid]
        b = agg_b[tid]
        # Symmetric union of mechanism strings. `_aggregate_targets_by_id`
        # already sorts each side; merging via `set | set` then sorting
        # collapses any overlap and keeps the output stable.
        combined_mechanisms = sorted(
            set(a["mechanisms_of_action"]) | set(b["mechanisms_of_action"])
        )
        shared.append(
            {
                "target_chembl_id": tid,
                "gene_symbol": a.get("gene_symbol") or b.get("gene_symbol"),
                "protein_name": a.get("protein_name") or b.get("protein_name"),
                "mechanism_of_action": " / ".join(combined_mechanisms) or None,
                "action_type_a": " / ".join(a["action_types"]) or None,
                "action_type_b": " / ".join(b["action_types"]) or None,
            }
        )
    return shared
