"""
CLI script to load DrugBank disease-drug relationships into the database.
"""

import argparse
import sys
from pathlib import Path

from drugbank_loader import (
    load_drugbank_data,
    save_disease_data_to_db,
    DRUGBANK_CACHE_DIR
)
from data_loader import load_from_database


def main():
    parser = argparse.ArgumentParser(
        description='Load DrugBank disease-drug relationships into BioNeighbor database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load Alzheimer's disease drugs (default)
  python load_drugbank_data.py

  # Load drugs for a specific disease
  python load_drugbank_data.py --disease "Parkinson's disease"

  # Load from DrugBank XML file
  python load_drugbank_data.py --xml-file data/drugbank_cache/drugbank.xml

  # Force reload (clear existing data)
  python load_drugbank_data.py --force

Notes:
  - DrugBank XML file can be downloaded from https://go.drugbank.com (requires registration)
  - Place the XML file in data/drugbank_cache/drugbank.xml
  - If no XML file is found, a curated sample of Alzheimer's drugs will be used
        """
    )
    
    parser.add_argument(
        '--disease',
        type=str,
        default="Alzheimer's disease",
        help='Disease name to load drugs for (default: "Alzheimer\'s disease")'
    )
    
    parser.add_argument(
        '--xml-file',
        type=str,
        help='Path to DrugBank XML file (if not in default location)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reload (clear existing disease data)'
    )
    
    parser.add_argument(
        '--no-sample',
        action='store_true',
        help='Do not use sample data if DrugBank XML not available'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("📥 Loading DrugBank Disease-Drug Relationships")
    print("=" * 60)
    print(f"Disease: {args.disease}")
    print(f"Force reload: {args.force}")
    print("=" * 60 + "\n")
    
    # Check if molecule database exists
    from data_loader import DB_PATH
    if not DB_PATH.exists():
        print("❌ Error: Molecules database not found.")
        print("   Please run 'python backend/main.py setup' first to create the molecule database.")
        sys.exit(1)
    
    # Load molecule database
    print("📂 Loading molecule database...")
    molecule_df = load_from_database()
    
    if molecule_df is None or len(molecule_df) == 0:
        print("❌ Error: No molecules found in database.")
        print("   Please run 'python backend/main.py setup' first to load molecules.")
        sys.exit(1)
    
    print(f"✅ Loaded {len(molecule_df)} molecules from database\n")
    
    # Handle XML file path
    if args.xml_file:
        xml_path = Path(args.xml_file)
        if not xml_path.exists():
            print(f"❌ Error: XML file not found: {xml_path}")
            sys.exit(1)
        
        # Copy or use the provided XML file
        target_xml = DRUGBANK_CACHE_DIR / "drugbank.xml"
        if xml_path != target_xml:
            import shutil
            print(f"📋 Copying XML file to cache directory...")
            shutil.copy2(xml_path, target_xml)
            print(f"✅ Copied to {target_xml}\n")
    
    # Clear existing data if force flag is set
    if args.force:
        print("⚠️  WARNING: --force will DELETE ALL disease and drug-disease relationship data!")
        print("   This affects the entire database, not just the specified disease.")
        response = input("   Type 'yes' to confirm: ")
        if response.lower() != 'yes':
            print("❌ Aborted. Use --force without confirmation to skip this prompt.")
            return
        
        print("🗑️  Clearing existing disease data...")
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM drug_diseases")
            cursor.execute("DELETE FROM diseases")
            conn.commit()
            print("✅ Cleared existing data\n")
        except sqlite3.OperationalError as e:
            print(f"⚠️  Could not clear existing data (tables may not exist yet): {e}\n")
        finally:
            conn.close()
    
    # Load DrugBank data
    print(f"📥 Loading DrugBank data for '{args.disease}'...")
    relationships = load_drugbank_data(
        target_disease=args.disease,
        use_sample=not args.no_sample
    )
    
    if not relationships:
        print("❌ No drug-disease relationships found.")
        print("\n💡 Tips:")
        print("   - Download DrugBank XML from https://go.drugbank.com")
        print(f"   - Place it at: {DRUGBANK_CACHE_DIR / 'drugbank.xml'}")
        print("   - Or use --xml-file to specify a different path")
        sys.exit(1)
    
    print(f"✅ Loaded {len(relationships)} drug-disease relationships\n")
    
    # Show sample relationships
    print("📋 Sample relationships:")
    for rel in relationships[:5]:
        print(f"  - {rel.get('drug_name', 'Unknown')} -> {rel.get('disease', 'Unknown')}")
    if len(relationships) > 5:
        print(f"  ... and {len(relationships) - 5} more\n")
    else:
        print()
    
    # Save to database
    print("💾 Saving to database...")
    stats = save_disease_data_to_db(relationships, molecule_df)
    
    print("\n" + "=" * 60)
    print("✅ DrugBank Data Loading Complete")
    print("=" * 60)
    print(f"Diseases added: {stats['diseases_added']}")
    print(f"Relationships added: {stats['relationships_added']}")
    print(f"Matched drugs: {stats['matched_drugs']}")
    print("=" * 60)
    
    if stats['matched_drugs'] == 0:
        print("\n⚠️  Warning: No drugs were matched to molecules in the database.")
        print("   This could mean:")
        print("   - The drugs are not in your molecule database")
        print("   - SMILES/InChI matching failed")
        print("   - Try loading more molecules first: python backend/main.py setup --max-molecules 50000")


if __name__ == "__main__":
    main()

