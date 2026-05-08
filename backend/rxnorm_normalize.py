"""
RxNorm name → ingredient normalization (issue #55).

Used by the Treatment Auditor to dedupe brand-vs-generic drug entries before
fanning out per-drug trial / AE / interaction fetches: "Taxol" and
"paclitaxel" should collapse to a single ingredient row.

Strategy per input name:
1. Local SQLite cache hit → return immediately.
2. RxNorm exact `/rxcui.json?name=<name>` lookup.
3. Fallback to RxNorm `/approximateTerm.json` (handles typos and brand
   variants the exact endpoint misses).
4. Resolve the resulting RXCUI to its ingredient (TTY=IN) via
   `/rxcui/<rxcui>/related.json?tty=IN`. The ingredient RXCUI is the dedupe
   key — anastrozole and Arimidex resolve to the same one.
5. Persist the result (positive *and* negative) so subsequent audits skip
   the network calls.

Reference:
- RxNorm REST API: https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html
"""

from __future__ import annotations

import concurrent.futures
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

import requests

from data_loader import DB_PATH

logger = logging.getLogger(__name__)

RXNORM_API_BASE = "https://rxnav.nlm.nih.gov/REST"
# Per-call HTTP timeout. RxNav is usually <500ms; pick something forgiving so
# a slow round-trip doesn't blow up the audit, but short enough that a hung
# server doesn't stall the user for tens of seconds.
HTTP_TIMEOUT = 6.0
# Minimum interval between live RxNorm calls (seconds). RxNav is generous,
# but a small gap keeps us polite when an audit lists many drugs.
RATE_LIMIT_DELAY = 0.05

CACHE_TABLE = "drug_rxnorm_cache"

# Bounded-parallelism settings for the cold-cache path. A single
# `_live_normalize` call can do up to 5 sequential HTTP requests
# (exact / approximate / properties / related / historystatus) each
# with HTTP_TIMEOUT seconds of patience — without parallelism a 10-drug
# audit with degraded RxNorm could stall the request for minutes.
NORMALIZE_MAX_WORKERS = 4
# Wall-clock cap for the entire batch's live lookups. Anything not done
# by this deadline is treated as a transient failure for THIS request
# (not cached) and the next audit retries.
NORMALIZE_BATCH_DEADLINE_SECS = 30.0


class RxNormLookupError(Exception):
    """Raised when an RxNorm lookup fails transiently (network error,
    non-200 HTTP, malformed JSON). Distinct from "the lookup succeeded
    and returned no match" — that case still returns `None` from the
    helpers. Callers MUST NOT cache results when this is raised, or a
    flaky network would freeze "no match" answers across future audits.
    """


def ensure_cache_table(conn: sqlite3.Connection) -> None:
    """Lazily create the cache table.

    Treatment Auditor users may run against a database that pre-dates the
    cache migration (or against a fresh dev database where migrations
    haven't been re-run). Creating it on demand here means the audit still
    works on those installs — at the cost of a one-time CREATE.
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CACHE_TABLE} (
            input_key TEXT PRIMARY KEY,
            input_name TEXT NOT NULL,
            rxcui TEXT,
            normalized_name TEXT,
            ingredient_rxcui TEXT,
            ingredient_name TEXT,
            matched INTEGER NOT NULL DEFAULT 0,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _input_key(name: str) -> str:
    return name.strip().lower()


def _cache_lookup(conn: sqlite3.Connection, key: str) -> Optional[Dict]:
    cursor = conn.execute(
        f"""
        SELECT rxcui, normalized_name, ingredient_rxcui, ingredient_name, matched
        FROM {CACHE_TABLE}
        WHERE input_key = ?
        """,
        (key,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "rxcui": row[0],
        "normalized_name": row[1],
        "ingredient_rxcui": row[2],
        "ingredient_name": row[3],
        "matched": bool(row[4]),
    }


def _cache_store(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    result: Dict,
) -> None:
    conn.execute(
        f"""
        INSERT OR REPLACE INTO {CACHE_TABLE}
            (input_key, input_name, rxcui, normalized_name, ingredient_rxcui, ingredient_name, matched, cached_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            key,
            name,
            result.get("rxcui"),
            result.get("normalized_name"),
            result.get("ingredient_rxcui"),
            result.get("ingredient_name"),
            1 if result.get("matched") else 0,
        ),
    )
    conn.commit()


def _rxcui_lookup_exact(name: str) -> Optional[str]:
    """RxNorm exact match by name.

    Returns the RXCUI string on a hit, `None` when the lookup succeeded
    but RxNorm has no exact match for this name (genuine no-match —
    safe to cache). Raises `RxNormLookupError` on any transient failure
    (network error, non-200 HTTP, malformed JSON) so callers can skip
    the cache write — a flaky network must not freeze "no match" for
    a real drug name.
    """
    try:
        resp = requests.get(
            f"{RXNORM_API_BASE}/rxcui.json",
            params={"name": name},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("RxNorm exact lookup failed for %r: %s", name, exc)
        raise RxNormLookupError(f"network error for {name!r}") from exc
    if resp.status_code != 200:
        logger.warning("RxNorm exact lookup HTTP %s for %r", resp.status_code, name)
        raise RxNormLookupError(f"HTTP {resp.status_code} for {name!r}")
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("RxNorm exact lookup returned non-JSON for %r", name)
        raise RxNormLookupError(f"non-JSON response for {name!r}") from exc
    ids = data.get("idGroup", {}).get("rxnormId") or []
    if isinstance(ids, list) and ids:
        return str(ids[0])
    return None


def _rxcui_lookup_approximate(name: str) -> Optional[str]:
    """RxNorm fuzzy match. Used when the exact endpoint returns nothing.

    Same convention as `_rxcui_lookup_exact`: returns RXCUI string on a
    hit, `None` for genuine no-match (cacheable), raises
    `RxNormLookupError` for transient failures (callers must skip the
    cache write).
    """
    try:
        resp = requests.get(
            f"{RXNORM_API_BASE}/approximateTerm.json",
            params={"term": name, "maxEntries": 1},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("RxNorm approximate lookup failed for %r: %s", name, exc)
        raise RxNormLookupError(f"network error for {name!r}") from exc
    if resp.status_code != 200:
        logger.warning("RxNorm approximate lookup HTTP %s for %r", resp.status_code, name)
        raise RxNormLookupError(f"HTTP {resp.status_code} for {name!r}")
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("RxNorm approximate lookup returned non-JSON for %r", name)
        raise RxNormLookupError(f"non-JSON response for {name!r}") from exc
    candidates = data.get("approximateGroup", {}).get("candidate") or []
    if isinstance(candidates, list) and candidates:
        rxcui = candidates[0].get("rxcui")
        if rxcui:
            return str(rxcui)
    return None


def _resolve_ingredient(rxcui: str) -> Optional[Dict[str, str]]:
    """Map an RXCUI to its ingredient (TTY=IN) RXCUI + name.

    For an ingredient input ("paclitaxel") the mapping is identity-ish
    (RxNorm returns the same concept). For a brand input ("Taxol") it
    returns the underlying ingredient — which is exactly the dedupe key
    we want.

    Returns the ingredient dict on success, `None` when the request
    succeeded but no IN concept was found (genuine — fall through to
    the historystatus fallback). Raises `RxNormLookupError` on any
    transient failure so the caller can skip writing a partial result
    to the cache.
    """
    try:
        resp = requests.get(
            f"{RXNORM_API_BASE}/rxcui/{rxcui}/related.json",
            params={"tty": "IN"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("RxNorm related-IN lookup failed for %s: %s", rxcui, exc)
        raise RxNormLookupError(f"network error for /related?tty=IN {rxcui}") from exc
    if resp.status_code != 200:
        logger.warning("RxNorm related-IN HTTP %s for %s", resp.status_code, rxcui)
        raise RxNormLookupError(f"HTTP {resp.status_code} for /related?tty=IN {rxcui}")
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("RxNorm related-IN returned non-JSON for %s", rxcui)
        raise RxNormLookupError(f"non-JSON for /related?tty=IN {rxcui}") from exc
    groups = data.get("relatedGroup", {}).get("conceptGroup") or []
    for group in groups:
        if group.get("tty") != "IN":
            continue
        concepts = group.get("conceptProperties") or []
        if concepts:
            top = concepts[0]
            return {
                "ingredient_rxcui": str(top.get("rxcui") or ""),
                "ingredient_name": top.get("name") or "",
            }
    return None


def _rxcui_properties(rxcui: str) -> Optional[Dict[str, str]]:
    """Fetch the canonical name + tty for an RXCUI.

    Returns the property dict on success, `None` when the request
    succeeded but the RXCUI has no properties record (genuine — happens
    for obsolete brand RXCUIs). Raises `RxNormLookupError` on transient
    failures.
    """
    try:
        resp = requests.get(
            f"{RXNORM_API_BASE}/rxcui/{rxcui}/properties.json",
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("RxNorm properties lookup failed for %s: %s", rxcui, exc)
        raise RxNormLookupError(f"network error for /properties {rxcui}") from exc
    if resp.status_code != 200:
        logger.warning("RxNorm properties HTTP %s for %s", resp.status_code, rxcui)
        raise RxNormLookupError(f"HTTP {resp.status_code} for /properties {rxcui}")
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("RxNorm properties returned non-JSON for %s", rxcui)
        raise RxNormLookupError(f"non-JSON for /properties {rxcui}") from exc
    props = data.get("properties") or {}
    if not props:
        return None
    return {
        "name": props.get("name") or "",
        "tty": props.get("tty") or "",
    }


def _historystatus(rxcui: str) -> Optional[Dict]:
    """Fetch RxNorm history/status for an RXCUI.

    `historystatus` is the single endpoint that works for *every* RXCUI,
    including obsolete brand-name concepts (e.g. discontinued brands like
    "Taxol", whose properties/related endpoints return empty payloads).
    Crucially, it carries `derivedConcepts.ingredientConcept[]` which is the
    only reliable bridge from an obsolete BN back to its active IN.

    Returns the history dict on success, `None` when the response was
    valid but contained no `rxcuiStatusHistory` (genuine — should be
    rare). Raises `RxNormLookupError` on transient failures.
    """
    try:
        resp = requests.get(
            f"{RXNORM_API_BASE}/rxcui/{rxcui}/historystatus.json",
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("RxNorm historystatus lookup failed for %s: %s", rxcui, exc)
        raise RxNormLookupError(f"network error for /historystatus {rxcui}") from exc
    if resp.status_code != 200:
        logger.warning("RxNorm historystatus HTTP %s for %s", resp.status_code, rxcui)
        raise RxNormLookupError(f"HTTP {resp.status_code} for /historystatus {rxcui}")
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("RxNorm historystatus returned non-JSON for %s", rxcui)
        raise RxNormLookupError(f"non-JSON for /historystatus {rxcui}") from exc
    return data.get("rxcuiStatusHistory") or None


def _live_normalize(name: str) -> Dict:
    """Hit RxNorm to normalize a single name. Returns a result dict.

    The dict always carries a `matched` boolean so the cache can store the
    negative case and avoid re-querying RxNorm for unknown drug names on
    subsequent audits.

    Propagates `RxNormLookupError` from the underlying lookup helpers so
    `normalize_drugs` can distinguish a transient failure (don't cache)
    from a genuine no-match (cacheable).
    """
    rxcui = _rxcui_lookup_exact(name)
    if not rxcui:
        time.sleep(RATE_LIMIT_DELAY)
        rxcui = _rxcui_lookup_approximate(name)

    if not rxcui:
        return {
            "matched": False,
            "rxcui": None,
            "normalized_name": None,
            "ingredient_rxcui": None,
            "ingredient_name": None,
        }

    time.sleep(RATE_LIMIT_DELAY)
    props = _rxcui_properties(rxcui) or {}
    normalized_name = props.get("name") or None
    tty = props.get("tty") or None

    ingredient_rxcui: Optional[str] = None
    ingredient_name: Optional[str] = None

    # Fast path: ask /related?tty=IN. Works for active concepts that are one
    # hop from an ingredient (SCD, SBD, BN→IN where the BN is current, etc.).
    time.sleep(RATE_LIMIT_DELAY)
    related = _resolve_ingredient(rxcui)
    if related:
        ingredient_rxcui = related.get("ingredient_rxcui") or None
        ingredient_name = related.get("ingredient_name") or None

    # Self-map for ingredient-tty inputs that have no /related rows pointing
    # back at themselves.
    if ingredient_rxcui is None and tty == "IN":
        ingredient_rxcui = rxcui
        ingredient_name = normalized_name

    # Fallback for obsolete BN concepts (e.g. discontinued brands like
    # "Taxol" → RXCUI 196466). /properties and /related return empty for
    # these, but /historystatus exposes the derived ingredient concept.
    if ingredient_rxcui is None:
        time.sleep(RATE_LIMIT_DELAY)
        history = _historystatus(rxcui) or {}
        derived = history.get("derivedConcepts") or {}
        ingredient_concepts = derived.get("ingredientConcept") or []
        if isinstance(ingredient_concepts, list) and ingredient_concepts:
            top = ingredient_concepts[0] or {}
            # Coerce empty strings to None so the dedupe-key fallback
            # logic in `_group_key` treats them as "no ingredient".
            ingredient_rxcui = top.get("ingredientRxcui") or None
            ingredient_name = top.get("ingredientName") or None
        # historystatus also carries the canonical name when properties was
        # empty — preserve it so the UI doesn't render `None`.
        if not normalized_name:
            attrs = history.get("attributes") or {}
            normalized_name = attrs.get("name") or None

    return {
        "matched": True,
        "rxcui": rxcui,
        "normalized_name": normalized_name,
        "ingredient_rxcui": ingredient_rxcui,
        "ingredient_name": ingredient_name,
    }


def _group_key(result: Dict, original_name: str) -> str:
    """Stable dedupe key callers use to collapse equivalent inputs.

    Prefers the ingredient RXCUI (collapses brand → generic). Falls back to
    the input RXCUI when no ingredient was found (rare — happens for
    multi-ingredient combo products). Falls back to the lowercased name
    when RxNorm couldn't match the input at all, so unknown drugs still
    appear as their own row instead of all collapsing to a single
    "unmatched" bucket.
    """
    if result.get("ingredient_rxcui"):
        return f"rxcui:{result['ingredient_rxcui']}"
    if result.get("rxcui"):
        return f"rxcui:{result['rxcui']}"
    return f"name:{_input_key(original_name)}"


def normalize_drugs(drugs: List[Dict]) -> List[Dict]:
    """Normalize a batch of `{name, chembl_id?}` rows.

    Each output row carries the original input fields back so the caller
    can correlate (Swift uses chembl_id when present and falls back to
    name). `group_key` is what the caller dedupes by.

    The function is best-effort: any RxNorm error for a single row is
    swallowed and surfaces as `matched=False`, so a flaky network can't
    block the audit.
    """
    if not drugs:
        return []

    # ------------------------------------------------------------------
    # Phase 1 — gather inputs in order and check the SQLite cache.
    # Sequential is fine here: cache hits are sub-millisecond and we
    # close the connection before the parallel phase so worker threads
    # never share the sqlite handle.
    # ------------------------------------------------------------------
    inputs: List[Dict[str, Any]] = []  # one entry per valid input drug
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        ensure_cache_table(conn)
        for entry in drugs:
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            key = _input_key(name)
            inputs.append({
                "name": name,
                "key": key,
                "chembl_id": entry.get("chembl_id"),
                "cached": _cache_lookup(conn, key),
            })
    finally:
        conn.close()
    if not inputs:
        return []

    # ------------------------------------------------------------------
    # Phase 2 — parallel live lookups for cache misses, with a shared
    # batch deadline so a degraded RxNorm service can't stall the
    # whole audit for minutes. Bounded worker count keeps us polite.
    # ------------------------------------------------------------------
    transient_unmatched: Dict[str, Optional[str]] = {
        "matched": False,
        "rxcui": None,
        "normalized_name": None,
        "ingredient_rxcui": None,
        "ingredient_name": None,
    }
    pending_indices = [i for i, e in enumerate(inputs) if e["cached"] is None]
    # `live_outcomes[i] = (result_dict, is_authoritative)`
    live_outcomes: Dict[int, tuple] = {}

    if pending_indices:
        # NOTE: deliberately not using `with ThreadPoolExecutor(...) as executor:`
        # — the context manager's __exit__ blocks until every submitted
        # task completes, defeating the deadline. We shut down with
        # `wait=False` so the function returns as soon as the deadline
        # fires; in-flight HTTP threads finish their work in the
        # background (their results are simply discarded — caches are
        # only written via the post-deadline `authoritative` path).
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=NORMALIZE_MAX_WORKERS
        )
        try:
            future_to_idx = {
                executor.submit(_live_normalize, inputs[i]["name"]): i
                for i in pending_indices
            }
            try:
                for future in concurrent.futures.as_completed(
                    future_to_idx, timeout=NORMALIZE_BATCH_DEADLINE_SECS
                ):
                    idx = future_to_idx[future]
                    name = inputs[idx]["name"]
                    try:
                        result = future.result()
                        live_outcomes[idx] = (result, True)
                    except RxNormLookupError as exc:
                        logger.warning(
                            "RxNorm transient error for %r — not caching: %s",
                            name, exc,
                        )
                        live_outcomes[idx] = (dict(transient_unmatched), False)
                    except Exception:
                        logger.exception(
                            "RxNorm normalize unexpected error for %r — not caching",
                            name,
                        )
                        live_outcomes[idx] = (dict(transient_unmatched), False)
            except concurrent.futures.TimeoutError:
                # `as_completed`'s timeout fired — fall through to the
                # cleanup loop which marks anything still pending as a
                # transient failure.
                pass
            # Anything still in flight after the deadline → transient.
            for future, idx in future_to_idx.items():
                if idx in live_outcomes:
                    continue
                future.cancel()
                logger.warning(
                    "RxNorm batch deadline exceeded for %r — not caching",
                    inputs[idx]["name"],
                )
                live_outcomes[idx] = (dict(transient_unmatched), False)
        finally:
            # `cancel_futures=True` is Python 3.9+; cancel anything still
            # queued but already-running tasks finish in the background.
            executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Phase 3 — persist authoritative live results. Done in a fresh
    # connection on the calling thread so we don't share sqlite handles
    # with the worker pool.
    # ------------------------------------------------------------------
    authoritative = [(idx, r) for idx, (r, auth) in live_outcomes.items() if auth]
    if authoritative:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            for idx, result in authoritative:
                _cache_store(conn, inputs[idx]["key"], inputs[idx]["name"], result)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Phase 4 — assemble output preserving original input order.
    # ------------------------------------------------------------------
    out: List[Dict] = []
    for idx, e in enumerate(inputs):
        if e["cached"] is not None:
            result = e["cached"]
        else:
            result, _ = live_outcomes[idx]
        group_key = _group_key(result, e["name"])
        out.append(
            {
                "input_name": e["name"],
                "input_chembl_id": e["chembl_id"],
                "rxcui": result.get("rxcui"),
                "normalized_name": result.get("normalized_name"),
                "ingredient_rxcui": result.get("ingredient_rxcui"),
                "ingredient_name": result.get("ingredient_name"),
                "matched": bool(result.get("matched")),
                "group_key": group_key,
            }
        )
    return out
