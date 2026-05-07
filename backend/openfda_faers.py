"""
OpenFDA FAERS adverse-event lookups for the Treatment Auditor (issue #46).

For each prescribed drug, return the top reported adverse events from
the FDA Adverse Event Reporting System and try to match the user's
self-reported symptoms against those terms — so the audit can say
"fatigue is among the top 5 reported reactions for tamoxifen".

Source: openFDA `/drug/event.json` — free, no API key needed for the
volume an audit needs (a few drugs at a time). Per-drug results are
cached in SQLite for 7 days because FAERS itself only updates quarterly,
so re-querying on every audit would waste network for stale data.

Reference: https://open.fda.gov/apis/drug/event/
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

import requests

from data_loader import DB_PATH

logger = logging.getLogger(__name__)

OPENFDA_EVENT_URL = "https://api.fda.gov/drug/event.json"
HTTP_TIMEOUT = 12.0

CACHE_TABLE = "drug_faers_cache"
# 7 days. FAERS releases quarterly; weekly refresh is more than enough.
CACHE_TTL_SECS = 7 * 24 * 60 * 60


def ensure_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CACHE_TABLE} (
            drug_key TEXT PRIMARY KEY,
            top_events_json TEXT NOT NULL,
            total_reports INTEGER NOT NULL DEFAULT 0,
            fetched_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def _drug_key(drug_name: str) -> str:
    return (drug_name or "").strip().lower()


def _cache_lookup(conn: sqlite3.Connection, key: str) -> Optional[Dict]:
    cur = conn.execute(
        f"SELECT top_events_json, total_reports, fetched_at FROM {CACHE_TABLE} WHERE drug_key = ?",
        (key,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    json_blob, total_reports, fetched_at = row
    if int(time.time()) - int(fetched_at or 0) > CACHE_TTL_SECS:
        return None
    try:
        return {
            "top_events": json.loads(json_blob),
            "total_reports": total_reports,
        }
    except (TypeError, ValueError):
        return None


def _cache_store(conn: sqlite3.Connection, key: str, top_events: List[Dict], total_reports: int) -> None:
    conn.execute(
        f"""
        INSERT OR REPLACE INTO {CACHE_TABLE} (drug_key, top_events_json, total_reports, fetched_at)
        VALUES (?, ?, ?, ?)
        """,
        (key, json.dumps(top_events), int(total_reports or 0), int(time.time())),
    )
    conn.commit()


def _live_top_events(drug_name: str, limit: int) -> Tuple[List[Dict], int]:
    """Hit OpenFDA for the top reaction terms for a drug.

    Uses the `count` aggregator on `patient.reaction.reactionmeddrapt` —
    OpenFDA returns `[{term, count}]` sorted descending. Same drug name
    may appear in either `generic_name` or `brand_name`; we OR them so
    "Taxol" and "paclitaxel" both work without normalization.

    Returns (top_events, total_reports). `total_reports` is a separate
    fetch (no aggregator → uses `meta.results.total`) so the UI can
    render "ranked among 12,345 reports" framing.
    """
    if not drug_name:
        return [], 0

    quoted = drug_name.replace("\"", "")
    search = (
        f'(patient.drug.openfda.generic_name:"{quoted}" '
        f'+patient.drug.openfda.brand_name:"{quoted}" '
        f'+patient.drug.medicinalproduct:"{quoted}")'
    )
    # Top events
    try:
        resp = requests.get(
            OPENFDA_EVENT_URL,
            params={
                "search": search,
                "count": "patient.reaction.reactionmeddrapt.exact",
                "limit": max(1, min(limit, 100)),
            },
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("OpenFDA top-events request failed for %r: %s", drug_name, exc)
        return [], 0

    if resp.status_code == 404:
        # OpenFDA returns 404 with `error.code = NOT_FOUND` when no
        # reports match — that's a clean "no data" signal, not an error.
        return [], 0
    if resp.status_code != 200:
        logger.warning("OpenFDA top-events HTTP %s for %r", resp.status_code, drug_name)
        return [], 0

    try:
        data = resp.json()
    except ValueError:
        return [], 0

    top_events = [
        {"term": str(row.get("term") or ""), "count": int(row.get("count") or 0)}
        for row in (data.get("results") or [])
        if row.get("term")
    ]

    # Total reports — separate request, smallest possible page size.
    total_reports = 0
    try:
        resp_total = requests.get(
            OPENFDA_EVENT_URL,
            params={"search": search, "limit": 1},
            timeout=HTTP_TIMEOUT,
        )
        if resp_total.status_code == 200:
            data_total = resp_total.json()
            total_reports = int(data_total.get("meta", {}).get("results", {}).get("total") or 0)
    except (requests.RequestException, ValueError):
        pass

    return top_events, total_reports


def get_top_events_for_drug(
    drug_name: str,
    limit: int = 25,
) -> Dict:
    """Public: return cached or fresh top adverse events for a drug.

    Result shape:
        {
            "drug_name": "...",
            "total_reports": int,
            "top_events": [{"term", "count"}, ...]
        }
    """
    key = _drug_key(drug_name)
    if not key:
        return {"drug_name": drug_name, "total_reports": 0, "top_events": []}

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        ensure_cache_table(conn)
        cached = _cache_lookup(conn, key)
        if cached is not None:
            return {
                "drug_name": drug_name,
                "total_reports": cached["total_reports"],
                "top_events": cached["top_events"][:limit],
            }
        top_events, total = _live_top_events(drug_name, limit=max(limit, 50))
        _cache_store(conn, key, top_events, total)
        return {
            "drug_name": drug_name,
            "total_reports": total,
            "top_events": top_events[:limit],
        }
    finally:
        conn.close()


def _symptom_to_term_match(symptom: str, events: List[Dict]) -> Optional[Dict]:
    """Find the FAERS event term most likely matching a free-text symptom.

    Strategy (cheap, deterministic):
      1. Exact case-insensitive match.
      2. The symptom is a substring of the term (e.g. "fatigue" inside
         "Fatigue increased").
      3. The term is a substring of the symptom (e.g. "rash" inside
         "skin rash").
      4. Any shared 4+ char token.

    Returns the highest-count match across all four passes (exact wins
    over substring wins over token), or None when nothing matches.
    """
    if not symptom or not events:
        return None
    s = symptom.strip().lower()
    if not s:
        return None

    s_tokens = {t for t in re_split_tokens(s) if len(t) >= 4}

    exact: Optional[Dict] = None
    sub_in_term: Optional[Dict] = None
    term_in_sym: Optional[Dict] = None
    token: Optional[Dict] = None

    for ev in events:
        term = (ev.get("term") or "").lower()
        if not term:
            continue
        if term == s:
            if exact is None or ev["count"] > exact["count"]:
                exact = ev
            continue
        if s in term:
            if sub_in_term is None or ev["count"] > sub_in_term["count"]:
                sub_in_term = ev
            continue
        if term in s:
            if term_in_sym is None or ev["count"] > term_in_sym["count"]:
                term_in_sym = ev
            continue
        if s_tokens:
            t_tokens = {t for t in re_split_tokens(term) if len(t) >= 4}
            if s_tokens & t_tokens:
                if token is None or ev["count"] > token["count"]:
                    token = ev

    return exact or sub_in_term or term_in_sym or token


def re_split_tokens(text: str) -> List[str]:
    """Split on whitespace + common punctuation. Stays as a small helper
    instead of pulling in a tokenizer."""
    import re
    return [t for t in re.split(r"[\s,.\-/()]+", text) if t]


def get_drug_event_panel(drugs: List[Dict], symptoms: List[str], top_n: int = 15) -> Dict:
    """Build the full FAERS panel the Treatment Auditor displays.

    `drugs` is `[{name, chembl_id?}]`. `symptoms` is a flat list of
    user-reported strings (no severity needed for matching).

    Returns:
        {
            "per_drug": [
                {"drug_name", "total_reports", "top_events": [...]}
            ],
            "symptom_matches": [
                {"drug_name", "symptom", "matched_term", "count",
                 "rank_in_top": int (1-indexed) | null,
                 "total_reports": int}
            ]
        }
    """
    per_drug = [get_top_events_for_drug(d.get("name", ""), limit=top_n) for d in drugs]

    symptom_matches: List[Dict] = []
    for entry in per_drug:
        events = entry.get("top_events") or []
        for sym in symptoms:
            sym = (sym or "").strip()
            if not sym:
                continue
            match = _symptom_to_term_match(sym, events)
            if match is None:
                continue
            try:
                rank = next(
                    i + 1
                    for i, ev in enumerate(events)
                    if (ev.get("term") or "").lower() == (match.get("term") or "").lower()
                )
            except StopIteration:
                rank = None
            symptom_matches.append(
                {
                    "drug_name": entry["drug_name"],
                    "symptom": sym,
                    "matched_term": match["term"],
                    "count": match["count"],
                    "rank_in_top": rank,
                    "total_reports": entry.get("total_reports", 0),
                }
            )

    # Stable ordering: drugs first, then by rank ascending so the top
    # matches surface first.
    symptom_matches.sort(
        key=lambda x: (
            x["drug_name"].lower(),
            x.get("rank_in_top") or 9999,
        )
    )

    return {"per_drug": per_drug, "symptom_matches": symptom_matches}
