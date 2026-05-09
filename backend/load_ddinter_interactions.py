"""
CLI to populate the local `drug_interactions` table from DDInter
(https://ddinter.scbdd.com).

Replaces the previous DrugBank loader. DDInter ships eight per-ATC-class
CSVs (~13 MB total); this script downloads them on demand into
`data/ddinter_cache/`, dedupes pairs, and bulk-loads into SQLite.

License: DDInter is published under CC BY-NC-SA 4.0 — non-commercial use
only, attribution required, derivative data works must be CC BY-NC-SA. The
project does NOT redistribute the CSVs; this script fetches them on the
operator's machine. Commercial users must NOT run this loader.

Usage:
    python load_ddinter_interactions.py
    python load_ddinter_interactions.py --refresh    # force re-download
"""

from __future__ import annotations

import argparse
import logging
import sys

from db_migrations import migrate_database
from ddinter_loader import (
    DDINTER_CACHE_DIR,
    populate_interactions_table,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate drug_interactions table from DDInter (ddinter.scbdd.com).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-download of the eight ATC-class CSVs (default: use cache when present).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("📥 Loading DDInter pairwise drug-drug interactions")
    print("=" * 60)
    print(f"Cache:  {DDINTER_CACHE_DIR}")
    print("License: CC BY-NC-SA 4.0 (non-commercial use only).")
    print("Source:  https://ddinter.scbdd.com/")
    print()

    print("🔧 Running migrations to ensure drug_interactions table exists...")
    if not migrate_database():
        print("❌ Database migration failed")
        return 1

    print("📖 Fetching CSVs and inserting interactions...")
    stats = populate_interactions_table(force_refresh=args.refresh)

    print()
    print("=" * 60)
    print("✅ DDInter Interaction Loading Complete")
    print("=" * 60)
    print(f"  Parsed pairs:   {stats['parsed']}")
    print(f"  Inserted pairs: {stats['inserted']}")
    print(f"  Skipped (dupe): {stats['skipped']}")
    print()
    print("Attribution required when redistributing audit reports:")
    print("  Drug-drug interaction data: DDInter (https://ddinter.scbdd.com), CC BY-NC-SA 4.0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
