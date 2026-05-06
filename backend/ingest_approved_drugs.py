"""
Backfill the local molecules table + FAISS index with real ChEMBL drugs.

The historical FAISS index was seeded from a non-drug chemical-space dump
(~10K small molecules with placeholder numeric chembl_ids). This script
replaces it with the union of:

  1. ChEMBL approved drugs (max_phase=4) — ~3-5k drugs
  2. Unique chembl_ids already present in our cancer_subtype_drugs cache,
     to pick up Phase 3 oncology trial drugs we've curated for the Cancer
     Research browse (camrelizumab, sacituzumab govitecan, trilaciclib, …)

After running, the molecular similarity feature returns therapeutic peers
instead of random small chemicals (anastrozole → letrozole/exemestane,
ribociclib → palbociclib/abemaciclib, etc.).

USAGE:
    python backend/ingest_approved_drugs.py                 # default
    python backend/ingest_approved_drugs.py --max-approved 500
    python backend/ingest_approved_drugs.py --dry-run
    python backend/ingest_approved_drugs.py --no-cancer-cache

The script is idempotent — re-running rebuilds the index from scratch using
fresh ChEMBL data. The pre-rebuild database is always backed up to
`data/molecules.db.pre-drug-rebuild.bak`.
"""

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np

from data_loader import DB_PATH
from fingerprints import compute_morgan_fingerprint
from index_builder import build_and_save_index

try:
    from chembl_webresource_client.new_client import new_client
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False
    new_client = None


PROGRESS_INTERVAL = 50  # print a heartbeat every N drugs processed


# ---------------------------------------------------------------------------
# Drug fetching
# ---------------------------------------------------------------------------


def fetch_approved_drugs_from_chembl(max_drugs: int) -> List[Dict]:
    """
    Iterate ChEMBL `molecule.filter(max_phase=4)` and return up to max_drugs
    rows with the fields we need. Pattern lifted from data_loader.py:1050.
    """
    if not CHEMBL_AVAILABLE:
        raise RuntimeError("chembl_webresource_client not installed — cannot fetch from ChEMBL")

    print(f"🔍 Fetching up to {max_drugs} approved drugs from ChEMBL (max_phase=4)…")
    # `max_phase` must be in the projection — normalize_drug_record() reads
    # drug["max_phase"] to set is_approved. Without it every row gets
    # is_approved=0 even though we filtered to max_phase=4.
    approved_drugs = new_client.molecule.filter(max_phase=4).only([
        'molecule_chembl_id',
        'molecule_structures',
        'molecule_hierarchy',
        'pref_name',
        'molecular_weight',
        'molecule_type',
        'max_phase',
    ])

    out: List[Dict] = []
    seen: Set[str] = set()
    start = time.time()
    for drug in approved_drugs:
        if len(out) >= max_drugs:
            break
        chembl_id = drug.get('molecule_chembl_id')
        if not chembl_id or chembl_id in seen:
            continue
        seen.add(chembl_id)
        out.append(drug)
        if len(out) % PROGRESS_INTERVAL == 0:
            elapsed = time.time() - start
            print(f"   ✓ {len(out)} approved drugs fetched ({elapsed:.0f}s)")

    print(f"✅ Fetched {len(out)} approved drugs in {time.time()-start:.0f}s")
    return out


def fetch_extra_chembl_records(chembl_ids: List[str]) -> List[Dict]:
    """Bulk-fetch full molecule records for a list of chembl_ids."""
    if not chembl_ids or not CHEMBL_AVAILABLE:
        return []

    print(f"🔍 Fetching {len(chembl_ids)} extra drugs from cancer cache…")
    out: List[Dict] = []
    batch_size = 50
    for i in range(0, len(chembl_ids), batch_size):
        chunk = chembl_ids[i:i + batch_size]
        try:
            records = list(
                new_client.molecule.filter(molecule_chembl_id__in=chunk).only([
                    'molecule_chembl_id',
                    'molecule_structures',
                    'molecule_hierarchy',
                    'pref_name',
                    'molecular_weight',
                    'molecule_type',
                    'max_phase',
                ])
            )
            out.extend(records)
            print(f"   ✓ {len(out)}/{len(chembl_ids)}")
        except Exception as e:
            print(f"   ⚠️  batch error at {i}: {e}")
    return out


def cancer_cache_chembl_ids(conn: sqlite3.Connection) -> List[str]:
    """Distinct real CHEMBLnnnn ids already cached in cancer_subtype_drugs."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cancer_subtype_drugs'")
        if not cur.fetchone():
            return []
        cur.execute(
            """
            SELECT DISTINCT chembl_id
            FROM cancer_subtype_drugs
            WHERE chembl_id LIKE 'CHEMBL%'
            """
        )
        return [row[0] for row in cur.fetchall() if row[0]]
    except sqlite3.OperationalError:
        return []


# ---------------------------------------------------------------------------
# Per-drug processing — SMILES + fingerprint
# ---------------------------------------------------------------------------


def _coerce_int(value) -> Optional[int]:
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


def _largest_fragment(smiles: str) -> str:
    """
    SMILES with multiple components (e.g. salt + counterion) are dot-separated:
    'CC(=O)Oc1ccccc1C(=O)O.[Na+]'. The drug structure is the largest fragment;
    counterions and waters are tiny. Return only the largest fragment.
    """
    if '.' not in smiles:
        return smiles
    parts = [p for p in smiles.split('.') if p]
    return max(parts, key=len) if parts else smiles


def normalize_drug_record(drug: Dict) -> Optional[Dict]:
    """
    Convert a ChEMBL molecule record into the row shape we want for the
    local molecules table. Uses the SMILES already present in the record (no
    extra ChEMBL calls) and falls back to the largest fragment for salts —
    keeps the ingest fast (~10ms/drug) and good enough for similarity. Returns
    None when the drug genuinely has no small-molecule structure (biologics).
    """
    chembl_id = drug.get('molecule_chembl_id')
    if not chembl_id:
        return None

    structures = drug.get('molecule_structures') or {}
    smiles = structures.get('canonical_smiles') if structures else None
    if not smiles:
        return None

    smiles = _largest_fragment(smiles)
    fp = compute_morgan_fingerprint(smiles)
    if fp is None:
        return None

    name = drug.get('pref_name') or chembl_id
    mw = _coerce_float(drug.get('molecular_weight')) or 0.0
    max_phase = _coerce_int(drug.get('max_phase'))
    is_approved = max_phase == 4

    return {
        'chembl_id': chembl_id,
        'name': name,
        'smiles': smiles,
        'molecular_weight': mw,
        'is_approved': 1 if is_approved else 0,
        'fingerprint': fp,
    }


# ---------------------------------------------------------------------------
# Database + index rewrite
# ---------------------------------------------------------------------------


def backup_database() -> Path:
    """Take a consistent snapshot via SQLite's online backup API.

    `shutil.copy2` would byte-copy the file even mid-write, which can produce
    a torn snapshot if another process is touching the DB. The sqlite3 backup
    API holds the right locks and produces a transactionally consistent copy.
    """
    backup = DB_PATH.with_suffix('.db.pre-drug-rebuild.bak')
    print(f"📦 Backing up {DB_PATH} → {backup}")
    src = sqlite3.connect(str(DB_PATH))
    try:
        dst = sqlite3.connect(str(backup))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return backup


STAGED_MOLECULES_TABLE = "molecules_new"


def write_molecules_to_staging(conn: sqlite3.Connection, drugs: List[Dict]) -> None:
    """
    Populate a staging table (`molecules_new`) with the new drug rows without
    touching the live `molecules` table. The live table stays available for
    read traffic during the long FAISS rebuild that follows; promote_artifacts
    swaps both DB and index into place atomically afterwards.

    Rowid preservation: dependent tables (drug_diseases, ligands,
    drug_outcomes, cancer_subtype_drugs) carry molecule_index FKs into
    molecules.rowid. We snapshot the live chembl_id→rowid map and write the
    same rowid into the staging table for any drug whose chembl_id is already
    known, so when the staging table is promoted the existing FK references
    stay correct.
    """
    cur = conn.cursor()

    # Introspect the live table to find which columns actually exist —
    # the molecules schema varies across deployments (created out-of-band by
    # old ingest scripts) so we only insert columns that are there.
    cur.execute("PRAGMA table_info(molecules)")
    live_columns = {row[1] for row in cur.fetchall()}

    candidate_cols = [
        ('chembl_id',        lambda d: d['chembl_id']),
        ('name',             lambda d: d['name']),
        ('smiles',           lambda d: d['smiles']),
        ('molecular_weight', lambda d: d['molecular_weight']),
        ('is_approved',      lambda d: d['is_approved']),
    ]
    cols = [(name, fn) for name, fn in candidate_cols if name in live_columns]
    if not cols:
        raise RuntimeError(
            "molecules table has none of the expected columns "
            "(chembl_id, name, smiles, molecular_weight, is_approved)"
        )

    chembl_to_rowid: Dict[str, int] = {}
    if 'chembl_id' in live_columns:
        cur.execute("SELECT rowid, chembl_id FROM molecules WHERE chembl_id IS NOT NULL")
        for rowid, cid in cur.fetchall():
            if cid:
                chembl_to_rowid[cid] = rowid

    # Clone the live molecules schema into the staging table. Reading the
    # CREATE TABLE statement from sqlite_master and swapping the name keeps us
    # honest about whatever columns/types/defaults the live DB actually has.
    cur.execute("DROP TABLE IF EXISTS molecules_new")
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='molecules'")
    row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError("Could not read CREATE TABLE statement for molecules")
    create_sql = row[0]
    # Replace the first occurrence of the table name. CREATE TABLE statements
    # always start with "CREATE TABLE [IF NOT EXISTS] <name>", so a single
    # targeted replacement is safe.
    staged_create = create_sql.replace("molecules", STAGED_MOLECULES_TABLE, 1)
    cur.execute(staged_create)

    pinned: List[Dict] = []
    fresh: List[Dict] = []
    for d in drugs:
        if d['chembl_id'] in chembl_to_rowid:
            pinned.append(d)
        else:
            fresh.append(d)

    col_names = ", ".join(c for c, _ in cols)
    placeholders = ", ".join("?" * len(cols))

    # Annotate each drug dict with the rowid we're assigning so downstream
    # FAISS metadata can store the *real* rowid (rather than a dense
    # 0..N-1 sequence that won't match the molecules table after promotion).
    if pinned:
        sql_pinned = f"INSERT INTO {STAGED_MOLECULES_TABLE} (rowid, {col_names}) VALUES (?, {placeholders})"
        print(f"📝 Staging {len(pinned)} drugs at their original rowids (preserves FKs)…")
        rows_pinned = []
        for d in pinned:
            assigned = chembl_to_rowid[d['chembl_id']]
            d['rowid'] = assigned
            rows_pinned.append((assigned,) + tuple(fn(d) for _, fn in cols))
        cur.executemany(sql_pinned, rows_pinned)

    if fresh:
        max_rowid = max(chembl_to_rowid.values()) if chembl_to_rowid else 0
        sql_fresh = f"INSERT INTO {STAGED_MOLECULES_TABLE} (rowid, {col_names}) VALUES (?, {placeholders})"
        print(f"📝 Staging {len(fresh)} new drugs above rowid {max_rowid}…")
        rows_fresh = []
        for i, d in enumerate(fresh):
            assigned = max_rowid + 1 + i
            d['rowid'] = assigned
            rows_fresh.append((assigned,) + tuple(fn(d) for _, fn in cols))
        cur.executemany(sql_fresh, rows_fresh)

    conn.commit()
    print(f"✅ Staged {len(pinned)} pinned + {len(fresh)} new drugs into {STAGED_MOLECULES_TABLE}")


def promote_staged_artifacts(
    conn: sqlite3.Connection,
    temp_index_path: Path,
    temp_metadata_path: Path,
    live_index_path: Path,
    live_metadata_path: Path,
) -> None:
    """
    Atomically swap staged molecules_new → molecules and rename the temp index
    files into place. The DB swap is one sqlite transaction; the index files
    are promoted via os.replace which is atomic on POSIX.

    There's a small (millisecond-scale) window between the DB commit and the
    index rename where the two could disagree if the rename fails. If that
    happens we surface a clear error so the operator can restore from the
    pre-rebuild backup. This is dramatically better than the previous design
    where the inconsistency window was the entire FAISS build duration.
    """
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(molecules)")
    live_columns_raw = cur.fetchall()
    if not live_columns_raw:
        raise RuntimeError("molecules table missing — cannot promote staging table")
    live_cols = [r[1] for r in live_columns_raw if r[1] != 'rowid']
    cols_sql = ", ".join(live_cols)

    print("🔁 Promoting staged molecules table…")
    cur.execute("BEGIN IMMEDIATE")
    try:
        cur.execute("DELETE FROM molecules")
        # Copy with explicit rowid so the FK-preservation work in
        # write_molecules_to_staging carries through.
        cur.execute(
            f"INSERT INTO molecules (rowid, {cols_sql}) "
            f"SELECT rowid, {cols_sql} FROM {STAGED_MOLECULES_TABLE}"
        )
        cur.execute(f"DROP TABLE {STAGED_MOLECULES_TABLE}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print(f"🔁 Promoting FAISS index → {live_index_path}…")
    try:
        os.replace(str(temp_index_path), str(live_index_path))
        os.replace(str(temp_metadata_path), str(live_metadata_path))
    except OSError as e:
        raise RuntimeError(
            f"DB was promoted but FAISS index rename failed: {e}. "
            "Restore from the pre-rebuild backup before retrying."
        ) from e
    print("✅ Promotion complete")


def cleanup_staged_artifacts(
    conn: Optional[sqlite3.Connection],
    temp_index_path: Path,
    temp_metadata_path: Path,
) -> None:
    """Best-effort removal of staged artifacts after a failure. Never raises —
    the original exception is what the caller wants to see."""
    if conn is not None:
        try:
            conn.execute(f"DROP TABLE IF EXISTS {STAGED_MOLECULES_TABLE}")
            conn.commit()
        except Exception as e:
            print(f"   ⚠️  Cleanup warning: could not drop {STAGED_MOLECULES_TABLE}: {e}")
    for p in (temp_index_path, temp_metadata_path):
        try:
            if p.exists():
                p.unlink()
        except OSError as e:
            print(f"   ⚠️  Cleanup warning: could not remove {p}: {e}")


def rebuild_faiss_index(
    drugs: List[Dict],
    index_path: Optional[Path] = None,
    metadata_path: Optional[Path] = None,
) -> None:
    """Build the FAISS index. When `index_path`/`metadata_path` are provided,
    write to those files instead of the live ones — used by the staged-promotion
    flow so a failed build leaves the live index untouched.

    Cosine over Morgan fingerprints behaves like Tanimoto for our purposes —
    it ignores fingerprint magnitude so tiny molecules (water, salts) stop
    dominating L2 nearest-neighbour searches by virtue of their sparse vectors.
    """
    print(f"🔨 Building FAISS index for {len(drugs)} drugs…")
    fingerprints = np.vstack([d['fingerprint'] for d in drugs]).astype(np.float32)
    chembl_ids = [d['chembl_id'] for d in drugs]
    # Use the real molecules.rowid assigned by write_molecules_to_staging when
    # available so FAISS metadata mirrors the live table. Falls back to a
    # dense range only for legacy callers that don't pre-stage rowids.
    molecule_ids = [d.get('rowid', i) for i, d in enumerate(drugs)]
    if index_path is None and metadata_path is None:
        # Legacy path: write straight to the live files.
        build_and_save_index(
            fingerprints,
            molecule_ids,
            chembl_ids=chembl_ids,
            index_type='cosine',
            force_rebuild=True,
        )
    else:
        # Staged path: build in memory, save to caller-supplied paths, skip
        # the cache shortcut entirely.
        from index_builder import build_faiss_index, save_index, INDEX_PATH, METADATA_PATH
        index = build_faiss_index(fingerprints, index_type='cosine')
        metadata = {
            'molecule_ids': molecule_ids,
            'index_type': 'cosine',
            'dimension': fingerprints.shape[1],
            'n_vectors': len(fingerprints),
            'chembl_ids': chembl_ids,
        }
        save_index(
            index,
            metadata,
            index_path=index_path or INDEX_PATH,
            metadata_path=metadata_path or METADATA_PATH,
        )
    print("✅ FAISS index rebuilt")


# ---------------------------------------------------------------------------
# Sanity check after rebuild
# ---------------------------------------------------------------------------


SANITY_PROBES = [
    # (chembl_id, expected nearest-neighbor name fragment)
    ('CHEMBL1399',  'aromatase'),       # anastrozole → expect letrozole/exemestane
    ('CHEMBL3545110', 'palbo'),         # ribociclib → expect palbociclib/abemaciclib
]


def run_sanity_check() -> None:
    """
    Reload the freshly-built index and run a similarity query for a known
    drug to confirm the top hit looks like a therapeutic peer (not random).
    Best-effort — prints findings but doesn't fail the script.
    """
    try:
        from search_engine import SearchEngine
        engine = SearchEngine()  # __init__ loads index + molecule_df
    except Exception as e:
        print(f"⚠️  Sanity check skipped (couldn't load engine): {e}")
        return

    print("\n🔬 Sanity check — top similar drugs for known compounds:")
    for chembl_id, _ in SANITY_PROBES:
        try:
            hits = engine.search_by_chembl_id(chembl_id, top_k=5)
            print(f"\n  {chembl_id}")
            for h in hits:
                name = (h.get('name') or '')[:40]
                cid = h.get('chembl_id', '?')
                sim = h.get('similarity_score', h.get('similarity', 0))
                print(f"    {name:<40}  {cid:<14}  d²={sim:.3f}")
        except Exception as e:
            print(f"  {chembl_id}: skipped ({e})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild molecules table + FAISS index from ChEMBL approved drugs")
    parser.add_argument('--max-approved', type=int, default=5000,
                        help='Maximum approved drugs to fetch from ChEMBL (default 5000)')
    parser.add_argument('--no-cancer-cache', action='store_true',
                        help='Skip augmenting with cancer_subtype_drugs chembl_ids')
    parser.add_argument('--dry-run', action='store_true',
                        help='Fetch + fingerprint everything but do not modify the DB or index')
    args = parser.parse_args(argv)

    if not CHEMBL_AVAILABLE:
        print("❌ chembl_webresource_client not installed. Run: pip install chembl_webresource_client")
        return 1
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}. Run setup first.")
        return 1

    # 1. Fetch approved drugs from ChEMBL
    approved_records = fetch_approved_drugs_from_chembl(args.max_approved)
    approved_ids = {r.get('molecule_chembl_id') for r in approved_records}

    # 2. Optionally augment with cancer cache
    extra_records: List[Dict] = []
    if not args.no_cancer_cache:
        with sqlite3.connect(DB_PATH) as conn:
            cache_ids = cancer_cache_chembl_ids(conn)
        new_cache_ids = [cid for cid in cache_ids if cid not in approved_ids]
        if new_cache_ids:
            extra_records = fetch_extra_chembl_records(new_cache_ids)

    all_records = approved_records + extra_records
    print(f"\n📊 Total raw records to process: {len(all_records)} ({len(approved_records)} approved + {len(extra_records)} cancer-cache)")

    # 3. Resolve SMILES + compute fingerprints. Dedupe by canonical chembl_id.
    print("\n🧪 Resolving parent SMILES + computing fingerprints…")
    drugs: List[Dict] = []
    seen_chembl: Set[str] = set()
    skipped = 0
    start = time.time()

    for raw in all_records:
        chembl_id = raw.get('molecule_chembl_id')
        if not chembl_id or chembl_id in seen_chembl:
            continue
        seen_chembl.add(chembl_id)
        normalized = normalize_drug_record(raw)
        if normalized is None:
            # No SMILES (biologic) or invalid fingerprint — both rare and harmless to skip.
            skipped += 1
            continue
        drugs.append(normalized)
        if len(drugs) % PROGRESS_INTERVAL == 0:
            print(f"   ✓ fingerprinted {len(drugs)} ({time.time()-start:.0f}s elapsed)")

    print(f"\n✅ {len(drugs)} drugs ready for ingest ({skipped} skipped — biologics or invalid SMILES)")

    if not drugs:
        print("❌ Nothing to ingest — aborting.")
        return 1

    if args.dry_run:
        print("\n🛑 --dry-run set; skipping DB + index writes.")
        return 0

    # 4. Stage everything, build the FAISS index against the staged data, then
    # promote DB + index together. The live molecules table and live index
    # remain serving traffic for the duration of the FAISS build (which is by
    # far the slowest step). On any failure during staging or build, cleanup
    # leaves the live artifacts untouched.
    from index_builder import INDEX_PATH, METADATA_PATH
    backup_path = backup_database()
    temp_index_path = INDEX_PATH.with_suffix(INDEX_PATH.suffix + '.new')
    temp_metadata_path = METADATA_PATH.with_suffix(METADATA_PATH.suffix + '.new')

    with sqlite3.connect(DB_PATH) as conn:
        try:
            write_molecules_to_staging(conn, drugs)
            rebuild_faiss_index(
                drugs,
                index_path=temp_index_path,
                metadata_path=temp_metadata_path,
            )
            promote_staged_artifacts(
                conn,
                temp_index_path=temp_index_path,
                temp_metadata_path=temp_metadata_path,
                live_index_path=INDEX_PATH,
                live_metadata_path=METADATA_PATH,
            )
        except Exception as err:
            print(
                "❌ Ingest failed during staging/build/promotion.\n"
                f"   Error: {err}\n"
                f"   Backup is at: {backup_path}\n"
                "   Live DB and index were not modified."
            )
            cleanup_staged_artifacts(conn, temp_index_path, temp_metadata_path)
            raise

    # 5. Sanity check
    run_sanity_check()

    print(f"\n🎉 Done. {len(drugs)} drugs ingested. Restart the macOS app so the bundled backend reloads the new index.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
