"""
CLI script to download disease-drug relationships from PubChem.
Downloads drugs for Alzheimer's disease and top 100 diseases.
"""

import argparse
import sys
import time
from pathlib import Path

from drugbank_loader import (
    load_drugbank_data,
    save_disease_data_to_db,
    load_top_100_diseases_drugs
)
from data_loader import load_from_database, DB_PATH
from pubchem_drug_loader import load_drugs_for_disease
from top_100_diseases import get_disease_by_name, get_alzheimers_drugs
from drug_schema import initialize_drug_schema


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
    
    # Initialize drug schema
    print("🔧 Initializing drug database schema...")
    initialize_drug_schema()
    print("✅ Drug schema initialized\n")
    
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
    all_drugs = []
    
    # Download Alzheimer's drugs
    if args.alzheimers_only:
        print("=" * 60)
        print("📥 Downloading Alzheimer's Disease Drugs")
        print("=" * 60)
        
        # Load complete drug information
        alzheimers_drug_names = get_alzheimers_drugs()
        print(f"📥 Loading complete drug information for {len(alzheimers_drug_names)} drugs...")
        
        drugs = load_drugs_for_disease(
            disease_name="Alzheimer's disease",
            known_drug_names=alzheimers_drug_names,
            molecule_df=molecule_df
        )
        
        if drugs:
            print(f"✅ Loaded {len(drugs)} complete drug records\n")
            all_drugs.extend(drugs)
            
            # Also create relationships from drugs
            for drug in drugs:
                all_relationships.append({
                    'drug_name': drug.get('name'),
                    'smiles': drug.get('smiles'),
                    'disease': "Alzheimer's disease",
                    'indication_type': 'approved',
                    'pubchem_cid': drug.get('pubchem_cid')
                })
        
        # Also load relationships (for backward compatibility)
        relationships = load_drugbank_data(
            target_disease="Alzheimer's disease",
            use_sample=False,
            use_pubchem=True
        )
        
        if relationships:
            print(f"✅ Loaded {len(relationships)} additional relationships\n")
            all_relationships.extend(relationships)
    
    # Download top 100 diseases
    if args.top_100:
        print("=" * 60)
        print(f"📥 Downloading Drugs for Top {args.max_diseases} Diseases")
        print("=" * 60)
        print("   This will take a while due to PubChem rate limiting...")
        print("   Progress will be shown for each disease.\n")
        
        try:
            from top_100_diseases import get_top_100_diseases
            diseases = get_top_100_diseases()[:args.max_diseases]
            
            for i, (disease_name, mesh_id, known_drugs) in enumerate(diseases, 1):
                if i == 1 and args.alzheimers_only:
                    # Skip Alzheimer's if already processed
                    continue
                
                print(f"\n[{i}/{len(diseases)}] Processing: {disease_name}")
                
                # Load complete drug information
                drugs = load_drugs_for_disease(
                    disease_name=disease_name,
                    known_drug_names=known_drugs[:args.max_drugs_per_disease],
                    molecule_df=molecule_df
                )
                
                if drugs:
                    all_drugs.extend(drugs)
                    for drug in drugs:
                        all_relationships.append({
                            'drug_name': drug.get('name'),
                            'smiles': drug.get('smiles'),
                            'disease': disease_name,
                            'indication_type': 'approved',
                            'pubchem_cid': drug.get('pubchem_cid')
                        })
                
                time.sleep(1)  # Rate limiting
        
        except Exception as e:
            print(f"⚠️  Error loading top diseases: {e}")
        
        # Also load relationships (for molecules)
        relationships = load_top_100_diseases_drugs(
            max_diseases=args.max_diseases,
            max_drugs_per_disease=args.max_drugs_per_disease,
            molecule_df=molecule_df
        )
        
        if relationships:
            print(f"\n✅ Loaded {len(relationships)} additional relationships")
            all_relationships.extend(relationships)
    
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
    stats = save_disease_data_to_db(unique_relationships, molecule_df, drugs=all_drugs if all_drugs else None)
    
    print("\n" + "=" * 60)
    print("✅ Disease-Drug Download Complete")
    print("=" * 60)
    print(f"Diseases added: {stats['diseases_added']}")
    print(f"Relationships added: {stats['relationships_added']}")
    print(f"Matched drugs: {stats['matched_drugs']}")
    if 'drugs_added' in stats:
        print(f"Drugs added: {stats['drugs_added']}")
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

