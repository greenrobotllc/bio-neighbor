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


def replace_molecules_table(conn: sqlite3.Connection, drugs: List[Dict]) -> None:
    """
    Wipe the molecules table and bulk-insert the new drugs in a single
    transaction. The live `molecules` table schema varies across deployments
    (it was created out-of-band by old ingestion scripts) so we introspect
    the column set and only insert columns that exist. Fingerprints aren't
    persisted to the table — the FAISS index file is the source of truth.

    Rowid preservation: dependent tables (drug_diseases, ligands, drug_outcomes,
    cancer_subtype_drugs) carry molecule_index FKs into molecules.rowid. A
    naive DELETE+INSERT would reassign rowids and silently invalidate every
    existing FK. We snapshot the old chembl_id→rowid map first and reuse the
    same rowid for any drug whose chembl_id is still present in the new set,
    so existing FK references stay correct.
    """
    cur = conn.cursor()

    # Introspect the live table to find which columns actually exist.
    cur.execute("PRAGMA table_info(molecules)")
    live_columns = {row[1] for row in cur.fetchall()}

    # The full set of columns we COULD populate from a drug record.
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

    # Snapshot existing chembl_id → rowid before we wipe.
    chembl_to_rowid: Dict[str, int] = {}
    if 'chembl_id' in live_columns:
        cur.execute("SELECT rowid, chembl_id FROM molecules WHERE chembl_id IS NOT NULL")
        for rowid, cid in cur.fetchall():
            if cid:
                chembl_to_rowid[cid] = rowid

    print("🧹 Truncating molecules table…")
    cur.execute("DELETE FROM molecules")

    # Two passes: first the drugs we can pin to a preserved rowid, then the
    # rest. Pinning uses an explicit rowid in the INSERT; new drugs fall
    # through to auto-rowid above the previous max so we never collide with
    # a preserved rowid.
    pinned: List[Dict] = []
    fresh: List[Dict] = []
    for d in drugs:
        if d['chembl_id'] in chembl_to_rowid:
            pinned.append(d)
        else:
            fresh.append(d)

    col_names = ", ".join(c for c, _ in cols)
    placeholders = ", ".join("?" * len(cols))

    if pinned:
        sql_pinned = f"INSERT INTO molecules (rowid, {col_names}) VALUES (?, {placeholders})"
        print(f"📝 Re-inserting {len(pinned)} drugs at their original rowids (preserves FKs)…")
        cur.executemany(
            sql_pinned,
            [
                (chembl_to_rowid[d['chembl_id']],) + tuple(fn(d) for _, fn in cols)
                for d in pinned
            ],
        )

    if fresh:
        # Force fresh rows above the previous max rowid so AUTOINCREMENT-style
        # gap avoidance can't hand out a rowid that collides with a pinned one.
        max_rowid = max(chembl_to_rowid.values()) if chembl_to_rowid else 0
        sql_fresh = f"INSERT INTO molecules (rowid, {col_names}) VALUES (?, {placeholders})"
        print(f"📝 Inserting {len(fresh)} new drugs above rowid {max_rowid}…")
        cur.executemany(
            sql_fresh,
            [
                (max_rowid + 1 + i,) + tuple(fn(d) for _, fn in cols)
                for i, d in enumerate(fresh)
            ],
        )

    conn.commit()
    print(f"✅ molecules table replaced ({len(pinned)} pinned, {len(fresh)} new)")


def rebuild_faiss_index(drugs: List[Dict]) -> None:
    print(f"🔨 Building FAISS index for {len(drugs)} drugs…")
    fingerprints = np.vstack([d['fingerprint'] for d in drugs]).astype(np.float32)
    chembl_ids = [d['chembl_id'] for d in drugs]
    molecule_ids = list(range(len(drugs)))
    # Cosine over Morgan fingerprints behaves like Tanimoto for our purposes —
    # it ignores fingerprint magnitude so tiny molecules (water, salts) stop
    # dominating L2 nearest-neighbour searches by virtue of their sparse vectors.
    build_and_save_index(
        fingerprints,
        molecule_ids,
        chembl_ids=chembl_ids,
        index_type='cosine',
        force_rebuild=True,
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

    # 4. Backup, replace molecules, rebuild index.
    #
    # Full staging-table + atomic-rename is a future improvement. The minimum
    # we need today is that an index-rebuild failure doesn't leave the DB
    # silently ahead of the index — surface the inconsistency loudly and point
    # the operator at the backup we just took so recovery is one cp away.
    backup_path = backup_database()
    with sqlite3.connect(DB_PATH) as conn:
        replace_molecules_table(conn, drugs)
    try:
        rebuild_faiss_index(drugs)
    except Exception as rebuild_err:
        print(
            "❌ FAISS index rebuild FAILED after the molecules table was "
            "already replaced. The DB and index are now out of sync.\n"
            f"   Error: {rebuild_err}\n"
            f"   Restore from backup: cp {backup_path} {DB_PATH}\n"
            "   Then re-run ingest_approved_drugs.",
        )
        raise

    # 5. Sanity check
    run_sanity_check()

    print(f"\n🎉 Done. {len(drugs)} drugs ingested. Restart the macOS app so the bundled backend reloads the new index.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
