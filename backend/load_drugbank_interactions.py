"""
CLI to populate the local `drug_interactions` cache from a DrugBank full XML
download (issue #47). Run once after dropping the XML at
`data/drugbank_cache/drugbank.xml` (or pass --xml-file).

DrugBank's full XML requires a free academic-use registration at
https://go.drugbank.com. The Open Data CSV does NOT carry interactions —
only the full XML does.

Usage:
    python load_drugbank_interactions.py
    python load_drugbank_interactions.py --xml-file /path/to/drugbank.xml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from db_migrations import migrate_database
from drugbank_interactions import (
    DRUGBANK_XML_DEFAULT_PATH,
    populate_interactions_table,
)

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate drug_interactions table from a DrugBank XML download.",
    )
    parser.add_argument(
        "--xml-file",
        type=str,
        default=str(DRUGBANK_XML_DEFAULT_PATH),
        help=f"Path to DrugBank XML (default: {DRUGBANK_XML_DEFAULT_PATH})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    xml_path = Path(args.xml_file)
    if not xml_path.exists():
        print(f"❌ DrugBank XML not found at {xml_path}")
        print(
            "   Register at https://go.drugbank.com and place the XML at the "
            f"default location ({DRUGBANK_XML_DEFAULT_PATH}) or pass --xml-file."
        )
        return 1

    print("=" * 60)
    print("📥 Loading DrugBank pairwise drug-drug interactions")
    print("=" * 60)
    print(f"XML:    {xml_path}")
    print()

    print("🔧 Running migrations to ensure drug_interactions table exists...")
    if not migrate_database():
        print("❌ Database migration failed")
        return 1

    print("📖 Streaming XML and inserting interactions...")
    stats = populate_interactions_table(xml_path=xml_path)

    print()
    print("=" * 60)
    print("✅ DrugBank Interaction Loading Complete")
    print("=" * 60)
    print(f"  Parsed pairs:   {stats['parsed']}")
    print(f"  Inserted pairs: {stats['inserted']}")
    print(f"  Skipped (dupe): {stats['skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
