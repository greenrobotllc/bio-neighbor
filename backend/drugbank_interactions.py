"""
DrugBank pairwise drug-drug interaction support for the Treatment Auditor
(issue #47).

This module is independent from `drugbank_loader.py` (which handles
disease-drug relationships) — interactions live in a separate XML element
and are queried in a different shape (pair lookup, not per-disease).

Data flow:
1. The user drops the full DrugBank XML at `data/drugbank_cache/drugbank.xml`
   (free for academic use after registration). The Open Data CSV does NOT
   carry interactions — only the full XML does.
2. `populate_interactions_table()` streams the XML and bulk-inserts every
   pairwise interaction into the `drug_interactions` table.
3. The Treatment Auditor calls `/cancer-research/v2/treatment-auditor/drug-interactions`
   with the deduped drug list. The endpoint matches inputs to DrugBank rows
   by name (case-insensitive) and returns interactions where *both* sides
   appear in the input — i.e. only the pairs the user is actually taking.

When the XML hasn't been loaded the endpoint returns `drugbank_loaded:false`
and the Swift UI surfaces a "data unavailable" hint instead of a misleading
"no interactions" message.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

try:
    from defusedxml import ElementTree as ET
except ImportError:  # pragma: no cover - dev fallback
    import xml.etree.ElementTree as ET

from data_loader import DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)

DRUGBANK_NS = "http://www.drugbank.ca"
DRUGBANK_XML_DEFAULT_PATH = DATA_DIR / "drugbank_cache" / "drugbank.xml"
TABLE_NAME = "drug_interactions"

# Severity heuristics. DrugBank's free description text doesn't carry a
# structured severity field, so we infer from keywords. False negatives are
# fine here — the UI just shows "Severity: unknown" rather than misclassifying.
_SEVERITY_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("severe", re.compile(r"\b(serious|severe|life-threatening|fatal|major|contraindicat)", re.I)),
    ("moderate", re.compile(r"\b(moderate|monitor closely|caution)", re.I)),
    ("minor", re.compile(r"\b(minor|mild)", re.I)),
]


def ensure_interactions_table(conn: sqlite3.Connection) -> None:
    """Create the table on demand so the migration order is forgiving."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_a_id TEXT NOT NULL,
            drug_a_name TEXT NOT NULL,
            drug_b_id TEXT NOT NULL,
            drug_b_name TEXT NOT NULL,
            description TEXT,
            severity TEXT,
            UNIQUE(drug_a_id, drug_b_id)
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_drug_interactions_a_name ON {TABLE_NAME}(LOWER(drug_a_name))"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_drug_interactions_b_name ON {TABLE_NAME}(LOWER(drug_b_name))"
    )
    conn.commit()


def _infer_severity(description: str) -> Optional[str]:
    if not description:
        return None
    for label, pattern in _SEVERITY_PATTERNS:
        if pattern.search(description):
            return label
    return None


def parse_drugbank_interactions(xml_path: Path) -> Iterable[Dict]:
    """Stream pairwise interactions out of a DrugBank XML file.

    Yields one dict per `<drug-interaction>` row. Memory-efficient: we
    `clear()` each parent `<drug>` element after handling it so the entire
    XML never has to fit in memory (the full release is ~1.5GB).
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"DrugBank XML not found at {xml_path}")

    drug_tag = f"{{{DRUGBANK_NS}}}drug"
    ddi_container_tag = f"{{{DRUGBANK_NS}}}drug-interactions"
    ddi_tag = f"{{{DRUGBANK_NS}}}drug-interaction"
    name_tag = f"{{{DRUGBANK_NS}}}name"
    drugbank_id_tag = f"{{{DRUGBANK_NS}}}drugbank-id"
    description_tag = f"{{{DRUGBANK_NS}}}description"

    context = ET.iterparse(xml_path, events=("start", "end"))
    context = iter(context)
    _, _ = next(context)  # drop the root start event

    for event, elem in context:
        # Only fire on top-level <drug> end events. DrugBank nests <drug>-shaped
        # tags inside other elements — the depth-1 tag is the one we want; the
        # iterparse stream's interleaving means we filter on tag name and
        # require the interactions container to be a direct child.
        if event != "end" or elem.tag != drug_tag:
            continue

        # Parent drug — only take direct children to avoid catching nested
        # `<drug>` elements (e.g. inside `<mixtures>`) as parents.
        primary_id_elem = elem.find(drugbank_id_tag)
        primary_name_elem = elem.find(name_tag)
        primary_id = primary_id_elem.text.strip() if primary_id_elem is not None and primary_id_elem.text else None
        primary_name = primary_name_elem.text.strip() if primary_name_elem is not None and primary_name_elem.text else None

        if not primary_id or not primary_name:
            elem.clear()
            continue

        ddi_container = elem.find(ddi_container_tag)
        if ddi_container is None:
            elem.clear()
            continue

        for ddi in ddi_container.findall(ddi_tag):
            partner_id_elem = ddi.find(drugbank_id_tag)
            partner_name_elem = ddi.find(name_tag)
            partner_desc_elem = ddi.find(description_tag)

            partner_id = partner_id_elem.text.strip() if partner_id_elem is not None and partner_id_elem.text else None
            partner_name = partner_name_elem.text.strip() if partner_name_elem is not None and partner_name_elem.text else None
            description = partner_desc_elem.text.strip() if partner_desc_elem is not None and partner_desc_elem.text else None

            if not partner_id or not partner_name:
                continue

            yield {
                "drug_a_id": primary_id,
                "drug_a_name": primary_name,
                "drug_b_id": partner_id,
                "drug_b_name": partner_name,
                "description": description,
                "severity": _infer_severity(description or ""),
            }

        # Free the element subtree we just processed.
        elem.clear()


def populate_interactions_table(
    xml_path: Optional[Path] = None,
    *,
    progress_every: int = 100_000,
) -> Dict[str, int]:
    """Bulk-load pairwise interactions from XML into SQLite.

    Returns a stats dict with `parsed`, `inserted`, `skipped`. `inserted`
    counts unique ordered pairs (DrugBank itself stores the same pair twice
    — once from each side; the UNIQUE constraint dedupes).
    """
    path = xml_path or DRUGBANK_XML_DEFAULT_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        ensure_interactions_table(conn)

        # Wipe-and-reload semantics. Interactions don't merge cleanly with
        # an old run because the source is one big monolithic XML — partial
        # updates make the cache inconsistent.
        conn.execute(f"DELETE FROM {TABLE_NAME}")
        conn.commit()

        parsed = 0
        inserted = 0
        skipped = 0
        cur = conn.cursor()

        # Normalize ordered pair so (A,B) and (B,A) collapse — DrugBank
        # stores both directions which would double our row count.
        seen: Set[Tuple[str, str]] = set()

        batch: List[Tuple] = []
        BATCH_SIZE = 5000

        for row in parse_drugbank_interactions(path):
            parsed += 1
            a, b = row["drug_a_id"], row["drug_b_id"]
            ordered = (a, b) if a < b else (b, a)
            if ordered in seen:
                skipped += 1
                continue
            seen.add(ordered)

            # Persist with the lexically-lower id as drug_a so the UNIQUE
            # constraint also enforces order canonicalization.
            if a > b:
                row["drug_a_id"], row["drug_b_id"] = row["drug_b_id"], row["drug_a_id"]
                row["drug_a_name"], row["drug_b_name"] = row["drug_b_name"], row["drug_a_name"]

            batch.append(
                (
                    row["drug_a_id"],
                    row["drug_a_name"],
                    row["drug_b_id"],
                    row["drug_b_name"],
                    row["description"],
                    row["severity"],
                )
            )
            inserted += 1

            if len(batch) >= BATCH_SIZE:
                cur.executemany(
                    f"INSERT OR IGNORE INTO {TABLE_NAME} "
                    "(drug_a_id, drug_a_name, drug_b_id, drug_b_name, description, severity) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    batch,
                )
                conn.commit()
                batch.clear()

            if parsed % progress_every == 0:
                logger.info(
                    "DrugBank DDI parse progress: parsed=%d inserted=%d skipped=%d",
                    parsed, inserted, skipped,
                )

        if batch:
            cur.executemany(
                f"INSERT OR IGNORE INTO {TABLE_NAME} "
                "(drug_a_id, drug_a_name, drug_b_id, drug_b_name, description, severity) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )
            conn.commit()

        return {"parsed": parsed, "inserted": inserted, "skipped": skipped}
    finally:
        conn.close()


def is_interactions_loaded() -> bool:
    """Cheap probe used by the API to decide whether to render the
    "DrugBank unavailable" hint. Returns True iff the table exists and
    has at least one row.
    """
    if not DB_PATH.exists():
        return False
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        )
        if cur.fetchone() is None:
            return False
        cur = conn.execute(f"SELECT 1 FROM {TABLE_NAME} LIMIT 1")
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_pairwise_interactions(drug_inputs: List[Dict]) -> Dict:
    """Return the pairwise interactions among the supplied drugs.

    Each input is `{"name": str, "chembl_id": str?, "drugbank_id": str?}`.
    Matching priority is drugbank_id → name (case-insensitive). Names that
    don't match anything in DrugBank are returned in `unmatched` so the UI
    can show "Couldn't match: X, Y" instead of silently dropping them.

    The shape mirrors what the Treatment Auditor needs:
        {
            "drugbank_loaded": True,
            "matched": [{"input_name": "...", "drugbank_id": "...", "drugbank_name": "..."}],
            "unmatched": ["..."],
            "interactions": [{"drug_a", "drug_b", "description", "severity"}, ...]
        }
    """
    if not drug_inputs:
        return {
            "drugbank_loaded": is_interactions_loaded(),
            "matched": [],
            "unmatched": [],
            "interactions": [],
        }

    if not is_interactions_loaded():
        return {
            "drugbank_loaded": False,
            "matched": [],
            "unmatched": [d.get("name", "") for d in drug_inputs if d.get("name")],
            "interactions": [],
        }

    conn = sqlite3.connect(DB_PATH)
    try:
        # Build a list of (input_name, drugbank_id, drugbank_name) for every
        # input we can resolve. Names match case-insensitively against either
        # drug_a_name or drug_b_name in the table.
        matched: List[Dict] = []
        unmatched: List[str] = []

        # First pass: collect distinct DrugBank IDs we've matched, keyed by
        # the *original* input name so the UI can correlate.
        for entry in drug_inputs:
            name = (entry.get("name") or "").strip()
            drugbank_id = (entry.get("drugbank_id") or "").strip() or None
            if not name and not drugbank_id:
                continue

            row = None
            if drugbank_id:
                cur = conn.execute(
                    f"""
                    SELECT drug_a_id, drug_a_name FROM {TABLE_NAME} WHERE drug_a_id = ? LIMIT 1
                    UNION
                    SELECT drug_b_id, drug_b_name FROM {TABLE_NAME} WHERE drug_b_id = ? LIMIT 1
                    """,
                    (drugbank_id, drugbank_id),
                )
                row = cur.fetchone()

            if row is None and name:
                # Case-insensitive name lookup. Either side of the pair is
                # a valid match — DrugBank stores names redundantly across
                # the table because the same drug appears as both `_a` and
                # `_b` across different rows.
                cur = conn.execute(
                    f"""
                    SELECT drug_a_id, drug_a_name FROM {TABLE_NAME}
                    WHERE LOWER(drug_a_name) = LOWER(?) LIMIT 1
                    """,
                    (name,),
                )
                row = cur.fetchone()
                if row is None:
                    cur = conn.execute(
                        f"""
                        SELECT drug_b_id, drug_b_name FROM {TABLE_NAME}
                        WHERE LOWER(drug_b_name) = LOWER(?) LIMIT 1
                        """,
                        (name,),
                    )
                    row = cur.fetchone()

            if row is None:
                unmatched.append(name)
                continue

            matched.append(
                {
                    "input_name": name or row[1],
                    "drugbank_id": row[0],
                    "drugbank_name": row[1],
                }
            )

        # Now fetch every interaction where both sides appear in `matched`.
        if len(matched) < 2:
            return {
                "drugbank_loaded": True,
                "matched": matched,
                "unmatched": unmatched,
                "interactions": [],
            }

        ids = [m["drugbank_id"] for m in matched]
        # Map DB id → display name preferring the user's *input* name so the
        # UI shows "Aspirin" instead of DrugBank's canonical capitalisation.
        id_to_input_name = {m["drugbank_id"]: m["input_name"] for m in matched}

        placeholders = ",".join(["?"] * len(ids))
        cur = conn.execute(
            f"""
            SELECT drug_a_id, drug_a_name, drug_b_id, drug_b_name, description, severity
            FROM {TABLE_NAME}
            WHERE drug_a_id IN ({placeholders}) AND drug_b_id IN ({placeholders})
            """,
            tuple(ids) + tuple(ids),
        )

        interactions = []
        for r in cur.fetchall():
            interactions.append(
                {
                    "drug_a_id": r[0],
                    "drug_a_name": id_to_input_name.get(r[0]) or r[1],
                    "drug_b_id": r[2],
                    "drug_b_name": id_to_input_name.get(r[2]) or r[3],
                    "description": r[4],
                    "severity": r[5],
                }
            )

        # Stable order for deterministic UI rendering: severe → moderate →
        # minor → unknown, then by drug names.
        severity_rank = {"severe": 0, "moderate": 1, "minor": 2, None: 3}
        interactions.sort(
            key=lambda x: (
                severity_rank.get(x.get("severity"), 3),
                (x.get("drug_a_name") or "").lower(),
                (x.get("drug_b_name") or "").lower(),
            )
        )

        return {
            "drugbank_loaded": True,
            "matched": matched,
            "unmatched": unmatched,
            "interactions": interactions,
        }
    finally:
        conn.close()
