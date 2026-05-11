"""
DDInter pairwise drug-drug interaction support for the Treatment Auditor.

Replaces the previous DrugBank XML-based loader (issue #47 → swap out per
DrugBank's "do not use to build products" terms). DDInter is published by
SCBDD under CC BY-NC-SA 4.0 and ships eight CSVs split by ATC class — total
~13MB, ~236k pairwise interactions across ~1.8k approved drugs.

Data flow:
1. `populate_interactions_table()` fetches the eight CSVs from
   ddinter.scbdd.com (or reads them from `data/ddinter_cache/` when already
   downloaded) and bulk-inserts into the `drug_interactions` SQLite table.
   Same table name and schema-compatible with the old DrugBank loader so the
   API layer didn't have to change.
2. The Treatment Auditor calls `/cancer-research/v2/treatment-auditor/drug-interactions`
   with the deduped drug list. The route matches inputs to DDInter rows by
   normalized name (lowercase + strip punctuation) and returns interactions
   where *both* sides appear in the input.

When the table hasn't been populated the endpoint returns
`drugbank_loaded:false` (kept under the legacy field name so the wire format
stays stable) and the UI surfaces a "data unavailable" hint instead of a
misleading "no interactions" message.

License note: DDInter is CC BY-NC-SA 4.0 — non-commercial use only.
The downloads themselves are not redistributed by this project; users fetch
them on their own machine. Commercial users must disable this loader.
"""

from __future__ import annotations

import csv
import logging
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from data_loader import DATA_DIR, DB_PATH

logger = logging.getLogger(__name__)

# DDInter ships per-ATC-class CSVs; URLs are static and unversioned.
DDINTER_BASE_URL = "https://ddinter.scbdd.com/static/media/download"
DDINTER_ATC_CLASSES = ("A", "B", "D", "H", "L", "P", "R", "V")
DDINTER_CACHE_DIR = DATA_DIR / "ddinter_cache"

TABLE_NAME = "drug_interactions"

# DDInter v1 uses Major/Moderate/Minor for the Level column. Lowercased so
# the wire format / CSS classes match the existing Swift severity scheme.
_VALID_LEVELS = {"major", "moderate", "minor"}

# Used to normalize names for matching. Strips parenthetical qualifiers and
# punctuation so "trastuzumab (mab)" and "Trastuzumab" collide.
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_name(name: str) -> str:
    """Lowercase, drop everything but alphanumerics. Stable across the
    loader and the query path so a row inserted as 'Trastuzumab' matches
    an input of 'trastuzumab' or 'Trastuzumab Inj.'"""
    return _NORMALIZE_RE.sub("", (name or "").lower())


def ensure_interactions_table(conn: sqlite3.Connection) -> None:
    """Create the table on demand. Schema is intentionally a superset of
    the DrugBank-era columns so rolling forward / back across the swap
    doesn't trip API consumers."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_a_id TEXT NOT NULL,
            drug_a_name TEXT NOT NULL,
            drug_a_norm TEXT NOT NULL,
            drug_b_id TEXT NOT NULL,
            drug_b_name TEXT NOT NULL,
            drug_b_norm TEXT NOT NULL,
            severity TEXT,
            description TEXT,
            UNIQUE(drug_a_id, drug_b_id)
        )
        """
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_ddi_a_norm ON {TABLE_NAME}(drug_a_norm)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_ddi_b_norm ON {TABLE_NAME}(drug_b_norm)")
    conn.commit()


def _fetch_csv(
    atc_class: str,
    *,
    cache_root: Optional[Path] = None,
    force_refresh: bool = False,
) -> Path:
    """Download one ATC-class CSV into the cache and return its path. Cache
    hits skip the network unless `force_refresh` is True. `cache_root`
    overrides the module-level default for this call only (tests pass a
    tempdir here)."""
    root = cache_root if cache_root is not None else DDINTER_CACHE_DIR
    root.mkdir(parents=True, exist_ok=True)
    filename = f"ddinter_downloads_code_{atc_class}.csv"
    cached = root / filename
    if cached.exists() and not force_refresh:
        logger.info("DDInter cache hit: %s", cached)
        return cached
    url = f"{DDINTER_BASE_URL}/{filename}"
    logger.info("Downloading %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bio-neighbor-ddinter-loader/1"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not download {url}: {e.reason}") from None
    cached.write_bytes(data)
    return cached


def parse_ddinter_csv(path: Path) -> Iterable[Dict]:
    """Yield one dict per row in a DDInter CSV. The schema has been stable
    since v1: `DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level`."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            id_a = (raw.get("DDInterID_A") or "").strip()
            id_b = (raw.get("DDInterID_B") or "").strip()
            name_a = (raw.get("Drug_A") or "").strip()
            name_b = (raw.get("Drug_B") or "").strip()
            level = (raw.get("Level") or "").strip().lower()
            if not (id_a and id_b and name_a and name_b):
                continue
            if level not in _VALID_LEVELS:
                # Unknown severity tokens — keep but tag as None so the
                # ranking logic doesn't try to sort them.
                level = None
            yield {
                "drug_a_id": id_a,
                "drug_a_name": name_a,
                "drug_b_id": id_b,
                "drug_b_name": name_b,
                "severity": level,
            }


def populate_interactions_table(
    *,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    progress_every: int = 50_000,
) -> Dict[str, int]:
    """Fetch all eight ATC CSVs and bulk-load into SQLite. Returns
    `{parsed, inserted, skipped}` for the loader CLI to print.

    Wipe-and-reload — partial updates would let stale rows linger when
    DDInter drops/renames a pair between releases.

    The reload is atomic: rows are staged into `drug_interactions_tmp`,
    and the live `drug_interactions` table is only touched at the end
    inside a single transaction that runs DELETE + INSERT-FROM-SELECT.
    If anything fails before that commit, the live table is unchanged
    and `is_interactions_loaded()` keeps reporting the prior state."""
    # Resolve cache root once, locally — don't mutate the module-level
    # DDINTER_CACHE_DIR (that override would leak to every subsequent
    # caller of _fetch_csv in this process).
    cache_root = cache_dir if cache_dir is not None else DDINTER_CACHE_DIR

    paths = [
        _fetch_csv(c, cache_root=cache_root, force_refresh=force_refresh)
        for c in DDINTER_ATC_CLASSES
    ]

    tmp_table = TABLE_NAME + "_tmp"
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        # DDL setup first so the upcoming DML transaction isn't broken up
        # by implicit commits triggered by CREATE/DROP. After this block
        # no transaction is open; the first executemany() below opens the
        # single implicit transaction that holds the entire load + swap.
        ensure_interactions_table(conn)
        conn.execute(f"DROP TABLE IF EXISTS {tmp_table}")
        conn.execute(
            f"""
            CREATE TABLE {tmp_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drug_a_id TEXT NOT NULL,
                drug_a_name TEXT NOT NULL,
                drug_a_norm TEXT NOT NULL,
                drug_b_id TEXT NOT NULL,
                drug_b_name TEXT NOT NULL,
                drug_b_norm TEXT NOT NULL,
                severity TEXT,
                description TEXT,
                UNIQUE(drug_a_id, drug_b_id)
            )
            """
        )
        conn.commit()

        parsed = 0
        inserted = 0
        skipped = 0
        cur = conn.cursor()
        # Pairs can legitimately appear in multiple ATC-class files when the
        # two drugs span classes. Dedupe by canonical-ordered ID pair.
        seen: Set[Tuple[str, str]] = set()
        batch: List[Tuple] = []
        BATCH_SIZE = 5000
        insert_sql = (
            f"INSERT OR IGNORE INTO {tmp_table} "
            "(drug_a_id, drug_a_name, drug_a_norm, "
            "drug_b_id, drug_b_name, drug_b_norm, "
            "severity, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )

        # Single implicit transaction from the first executemany() through
        # the final conn.commit() below. No intermediate commits, so
        # TABLE_NAME stays untouched until the atomic swap lands.
        for path in paths:
            for row in parse_ddinter_csv(path):
                parsed += 1
                a, b = row["drug_a_id"], row["drug_b_id"]
                ordered = (a, b) if a < b else (b, a)
                if ordered in seen:
                    skipped += 1
                    continue
                seen.add(ordered)

                if a > b:
                    row["drug_a_id"], row["drug_b_id"] = row["drug_b_id"], row["drug_a_id"]
                    row["drug_a_name"], row["drug_b_name"] = row["drug_b_name"], row["drug_a_name"]

                batch.append((
                    row["drug_a_id"],
                    row["drug_a_name"],
                    _normalize_name(row["drug_a_name"]),
                    row["drug_b_id"],
                    row["drug_b_name"],
                    _normalize_name(row["drug_b_name"]),
                    row["severity"],
                    None,  # description — DDInter v1 has no free-text per-pair
                ))
                inserted += 1

                if len(batch) >= BATCH_SIZE:
                    cur.executemany(insert_sql, batch)
                    batch.clear()

                if parsed % progress_every == 0:
                    logger.info(
                        "DDInter parse progress: parsed=%d inserted=%d skipped=%d",
                        parsed, inserted, skipped,
                    )

        if batch:
            cur.executemany(insert_sql, batch)

        # Atomic swap inside the same open transaction: DELETE on
        # TABLE_NAME runs only here, then INSERT-FROM-SELECT pulls the
        # staged rows across, then conn.commit() flips visibility in one
        # step. Readers see the prior rows until commit and the new rows
        # the instant after — never a half-loaded state.
        cur.execute(f"DELETE FROM {TABLE_NAME}")
        cur.execute(
            f"INSERT INTO {TABLE_NAME} "
            "(drug_a_id, drug_a_name, drug_a_norm, "
            " drug_b_id, drug_b_name, drug_b_norm, "
            " severity, description) "
            "SELECT drug_a_id, drug_a_name, drug_a_norm, "
            "       drug_b_id, drug_b_name, drug_b_norm, "
            "       severity, description "
            f"FROM {tmp_table}"
        )
        conn.commit()

        # Cleanup outside the transactional region. If this fails the
        # load is still complete; the next run's DROP IF EXISTS clears
        # the stale staging table.
        conn.execute(f"DROP TABLE IF EXISTS {tmp_table}")
        conn.commit()

        return {"parsed": parsed, "inserted": inserted, "skipped": skipped}
    except Exception:
        # Pre-swap failure: nothing was committed against TABLE_NAME, so
        # the live table is unchanged. Best-effort tmp cleanup so the
        # next attempt starts clean.
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        try:
            conn.execute(f"DROP TABLE IF EXISTS {tmp_table}")
            conn.commit()
        except sqlite3.Error:
            logger.exception("DDInter loader: failed to drop temp table during error cleanup")
        raise
    finally:
        conn.close()


def is_interactions_loaded() -> bool:
    """Cheap probe for the API. Returns True iff the table exists and has
    at least one row. Used to decide whether to render the 'data
    unavailable' hint."""
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
    DDInter has no ChEMBL or DrugBank cross-references — matching is by
    normalized drug name. Inputs that don't match a DDInter row are
    returned in `unmatched`.

    The shape mirrors what the wire format expects:
        {
            "drugbank_loaded": True,           # legacy field name; means "DDI data available"
            "data_source": "ddinter",          # new — lets the UI label correctly
            "matched":   [{"input_name", "ddinter_id", "ddinter_name"}],
            "unmatched": ["..."],
            "interactions": [{"drug_a", "drug_b", "severity", "description"}, ...]
        }
    """
    if not drug_inputs:
        return {
            "drugbank_loaded": is_interactions_loaded(),
            "data_source": "ddinter",
            "matched": [],
            "unmatched": [],
            "interactions": [],
        }

    if not is_interactions_loaded():
        return {
            "drugbank_loaded": False,
            "data_source": "ddinter",
            "matched": [],
            "unmatched": [d.get("name", "") for d in drug_inputs if d.get("name")],
            "interactions": [],
        }

    conn = sqlite3.connect(DB_PATH)
    try:
        matched: List[Dict] = []
        unmatched: List[str] = []

        for entry in drug_inputs:
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            norm = _normalize_name(name)
            if not norm:
                unmatched.append(name)
                continue

            cur = conn.execute(
                f"""
                SELECT drug_a_id, drug_a_name FROM {TABLE_NAME}
                WHERE drug_a_norm = ? LIMIT 1
                """,
                (norm,),
            )
            row = cur.fetchone()
            if row is None:
                cur = conn.execute(
                    f"""
                    SELECT drug_b_id, drug_b_name FROM {TABLE_NAME}
                    WHERE drug_b_norm = ? LIMIT 1
                    """,
                    (norm,),
                )
                row = cur.fetchone()
            if row is None:
                unmatched.append(name)
                continue

            matched.append({
                "input_name": name,
                "ddinter_id": row[0],
                "ddinter_name": row[1],
            })

        if len(matched) < 2:
            return {
                "drugbank_loaded": True,
                "data_source": "ddinter",
                "matched": matched,
                "unmatched": unmatched,
                "interactions": [],
            }

        ids = [m["ddinter_id"] for m in matched]
        id_to_input_name = {m["ddinter_id"]: m["input_name"] for m in matched}

        placeholders = ",".join(["?"] * len(ids))
        cur = conn.execute(
            f"""
            SELECT drug_a_id, drug_a_name, drug_b_id, drug_b_name, severity
            FROM {TABLE_NAME}
            WHERE drug_a_id IN ({placeholders}) AND drug_b_id IN ({placeholders})
            """,
            tuple(ids) + tuple(ids),
        )

        interactions = []
        for r in cur.fetchall():
            interactions.append({
                "drug_a_id": r[0],
                "drug_a_name": id_to_input_name.get(r[0]) or r[1],
                "drug_b_id": r[2],
                "drug_b_name": id_to_input_name.get(r[2]) or r[3],
                "severity": r[4],
                # DDInter has no per-pair description; the consumer renders
                # an empty cell in that column.
                "description": None,
            })

        # Sort: major → moderate → minor → unknown, then alpha.
        severity_rank = {"major": 0, "moderate": 1, "minor": 2, None: 3}
        interactions.sort(
            key=lambda x: (
                severity_rank.get(x.get("severity"), 3),
                (x.get("drug_a_name") or "").lower(),
                (x.get("drug_b_name") or "").lower(),
            )
        )

        return {
            "drugbank_loaded": True,
            "data_source": "ddinter",
            "matched": matched,
            "unmatched": unmatched,
            "interactions": interactions,
        }
    finally:
        conn.close()
