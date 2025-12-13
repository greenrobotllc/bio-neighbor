"""
CLI script to download disease-drug relationships from PubChem.
Downloads drugs for Alzheimer's disease and top 100 diseases.
"""

import argparse
import sys
from pathlib import Path

from drugbank_loader import (
    load_drugbank_data,
    save_disease_data_to_db,
    load_top_100_diseases_drugs
)
from data_loader import load_from_database


def main():
    parser = argparse.ArgumentParser(
        description='Download disease-drug relationships from PubChem',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download Alzheimer's disease drugs only
  python download_disease_drugs.py --alzheimers-only

  # Download drugs for top 100 diseases
  python download_disease_drugs.py --top-100

  # Download both Alzheimer's and top 100
  python download_disease_drugs.py --alzheimers-only --top-100

  # Limit number of diseases for top 100
  python download_disease_drugs.py --top-100 --max-diseases 50

Notes:
  - Uses PubChem API (pubchempy) which has worked reliably
  - Downloads may take time due to rate limiting
  - Drugs are matched to existing molecules in database
        """
    )
    
    parser.add_argument(
        '--alzheimers-only',
        action='store_true',
        help='Download only Alzheimer\'s disease drugs'
    )
    
    parser.add_argument(
        '--top-100',
        action='store_true',
        help='Download drugs for top 100 diseases'
    )
    
    parser.add_argument(
        '--max-diseases',
        type=int,
        default=100,
        help='Maximum number of diseases to process for top 100 (default: 100)'
    )
    
    parser.add_argument(
        '--max-drugs-per-disease',
        type=int,
        default=20,
        help='Maximum drugs per disease (default: 20)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reload (clear existing disease data)'
    )
    
    args = parser.parse_args()
    
    if not args.alzheimers_only and not args.top_100:
        # Default: do both
        args.alzheimers_only = True
        args.top_100 = True
    
    print("=" * 60)
    print("📥 Downloading Disease-Drug Relationships from PubChem")
    print("=" * 60)
    print(f"Alzheimer's only: {args.alzheimers_only}")
    print(f"Top 100 diseases: {args.top_100}")
    if args.top_100:
        print(f"Max diseases: {args.max_diseases}")
        print(f"Max drugs per disease: {args.max_drugs_per_disease}")
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
    
    # Clear existing data if force flag is set
    if args.force:
        print("🗑️  Clearing existing disease data...")
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM drug_diseases")
        cursor.execute("DELETE FROM diseases")
        conn.commit()
        conn.close()
        print("✅ Cleared existing data\n")
    
    all_relationships = []
    
    # Download Alzheimer's drugs
    if args.alzheimers_only:
        print("=" * 60)
        print("📥 Downloading Alzheimer's Disease Drugs")
        print("=" * 60)
        
        relationships = load_drugbank_data(
            target_disease="Alzheimer's disease",
            use_sample=False,  # Use PubChem instead
            use_pubchem=True
        )
        
        if relationships:
            print(f"✅ Loaded {len(relationships)} Alzheimer's disease drugs\n")
            all_relationships.extend(relationships)
        else:
            print("⚠️  No Alzheimer's drugs found\n")
    
    # Download top 100 diseases
    if args.top_100:
        print("=" * 60)
        print(f"📥 Downloading Drugs for Top {args.max_diseases} Diseases")
        print("=" * 60)
        print("   This will take a while due to PubChem rate limiting...")
        print("   Progress will be shown for each disease.\n")
        
        relationships = load_top_100_diseases_drugs(
            max_diseases=args.max_diseases,
            max_drugs_per_disease=args.max_drugs_per_disease,
            molecule_df=molecule_df
        )
        
        if relationships:
            print(f"\n✅ Loaded {len(relationships)} total drug-disease relationships")
            all_relationships.extend(relationships)
        else:
            print("\n⚠️  No drugs found for top diseases")
    
    if not all_relationships:
        print("\n❌ No drug-disease relationships found.")
        print("\n💡 Tips:")
        print("   - Ensure PubChem API is accessible")
        print("   - Check internet connection")
        print("   - Try running with --alzheimers-only first")
        sys.exit(1)
    
    # Remove duplicates (by drug name + disease)
    print(f"\n📊 Processing {len(all_relationships)} relationships...")
    seen = set()
    unique_relationships = []
    for rel in all_relationships:
        key = (rel.get('drug_name', ''), rel.get('disease', ''))
        if key not in seen:
            seen.add(key)
            unique_relationships.append(rel)
    
    print(f"✅ {len(unique_relationships)} unique relationships after deduplication\n")
    
    # Save to database
    print("💾 Saving to database...")
    stats = save_disease_data_to_db(unique_relationships, molecule_df)
    
    print("\n" + "=" * 60)
    print("✅ Disease-Drug Download Complete")
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
    else:
        print(f"\n✅ Successfully matched {stats['matched_drugs']} drugs to molecules!")
        print("   You can now browse diseases in the Mac app.")


if __name__ == "__main__":
    main()

