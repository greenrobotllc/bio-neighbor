"""
Generic script to download specific items by name.
Supports molecules, drugs, and diseases.
"""

import argparse
import sys
from pathlib import Path
from typing import List

from download_molecules import download_molecules_by_names
from pubchem_drug_loader import load_drug_info
from pubchem_disease_loader import search_drugs_by_disease
from drugbank_loader import save_drugs_to_db, save_disease_data_to_db
from data_loader import load_from_database, DB_PATH
from top_100_diseases import get_top_100_diseases


def download_molecules(names: List[str]) -> int:
    """
    Download molecules by name.
    
    Args:
        names: List of molecule names
        
    Returns:
        Number of molecules downloaded
    """
    print(f"📥 Downloading {len(names)} molecules by name...")
    df = download_molecules_by_names(names)
    
    if df is None or len(df) == 0:
        return 0
    
    # Save to database
    from data_loader import save_to_database
    existing_df = load_from_database()
    if existing_df is not None and len(existing_df) > 0:
        import pandas as pd
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        if 'pubchem_cid' in combined_df.columns:
            combined_df = combined_df.drop_duplicates(subset=['pubchem_cid'], keep='first')
        else:
            combined_df = combined_df.drop_duplicates(subset=['chembl_id'], keep='first')
        save_to_database(combined_df)
    else:
        save_to_database(df)
    
    return len(df)


def download_drugs(names: List[str]) -> int:
    """
    Download drugs by name.
    
    Args:
        names: List of drug names
        
    Returns:
        Number of drugs downloaded
    """
    print(f"📥 Downloading {len(names)} drugs by name...")
    
    molecule_df = load_from_database()
    drugs = []
    
    for i, name in enumerate(names, 1):
        name = name.strip()
        if not name:
            continue
        
        print(f"  [{i}/{len(names)}] Downloading: {name}")
        
        try:
            drug_info = load_drug_info(name, molecule_df=molecule_df)
            
            if drug_info:
                drugs.append(drug_info)
                print(f"    ✓ Downloaded: {drug_info.get('name', name)}")
            else:
                print(f"    ⚠️  Not found: {name}")
        
        except Exception as e:
            print(f"    ⚠️  Error downloading '{name}': {e}")
            continue
    
    if drugs:
        save_drugs_to_db(drugs)
        print(f"✅ Downloaded {len(drugs)}/{len(names)} drugs")
        return len(drugs)
    else:
        print("❌ No drugs downloaded")
        return 0


def download_diseases(names: List[str], max_drugs_per_disease: int = 10) -> int:
    """
    Download diseases and their associated drugs.
    
    Args:
        names: List of disease names
        max_drugs_per_disease: Maximum drugs to download per disease
        
    Returns:
        Number of diseases processed
    """
    print(f"📥 Downloading {len(names)} diseases and their drugs...")
    
    molecule_df = load_from_database()
    relationships = []
    all_drugs = []
    
    for i, disease_name in enumerate(names, 1):
        disease_name = disease_name.strip()
        if not disease_name:
            continue
        
        print(f"  [{i}/{len(names)}] Processing: {disease_name}")
        
        try:
            # Search for drugs for this disease
            drugs = search_drugs_by_disease(disease_name, max_drugs=max_drugs_per_disease)
            
            if drugs:
                # Load drug information
                drug_names = [d.get('drug_name') for d in drugs if d.get('drug_name')]
                
                for drug_name in drug_names[:max_drugs_per_disease]:
                    try:
                        drug_info = load_drug_info(drug_name, molecule_df=molecule_df)
                        if drug_info:
                            drug_info['disease'] = disease_name
                            all_drugs.append(drug_info)
                            relationships.append({
                                'drug_name': drug_info.get('name'),
                                'smiles': drug_info.get('smiles'),
                                'disease': disease_name,
                                'indication_type': 'approved',
                                'pubchem_cid': drug_info.get('pubchem_cid')
                            })
                    except Exception as e:
                        continue
                
                print(f"    ✓ Found {len([d for d in relationships if d.get('disease') == disease_name])} drugs for {disease_name}")
            else:
                print(f"    ⚠️  No drugs found for {disease_name}")
        
        except Exception as e:
            print(f"    ⚠️  Error processing '{disease_name}': {e}")
            continue
    
    if relationships:
        save_disease_data_to_db(relationships, molecule_df, drugs=all_drugs if all_drugs else None)
        print(f"✅ Processed {len(set(r.get('disease') for r in relationships))} diseases")
        return len(set(r.get('disease') for r in relationships))
    else:
        print("❌ No diseases processed")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description='Download specific items by name',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download molecules by name
  python download_by_name.py molecules --names "aspirin,ibuprofen"
  
  # Download drugs by name
  python download_by_name.py drugs --names "donepezil,rivastigmine"
  
  # Download diseases by name
  python download_by_name.py diseases --names "Alzheimer's disease,diabetes"
        """
    )
    
    try:
    
    subparsers = parser.add_subparsers(dest='type', help='Type of item to download')
    
    # Molecules parser
    molecules_parser = subparsers.add_parser('molecules', help='Download molecules')
    molecules_parser.add_argument('--names', type=str, required=True,
                                 help='Comma-separated list of molecule names')
    
    # Drugs parser
    drugs_parser = subparsers.add_parser('drugs', help='Download drugs')
    drugs_parser.add_argument('--names', type=str, required=True,
                             help='Comma-separated list of drug names')
    
    # Diseases parser
    diseases_parser = subparsers.add_parser('diseases', help='Download diseases')
    diseases_parser.add_argument('--names', type=str, required=True,
                                help='Comma-separated list of disease names')
    diseases_parser.add_argument('--max-drugs', type=int, default=10,
                                help='Maximum drugs per disease (default: 10)')
    
    args = parser.parse_args()
    
    if not args.type:
        parser.print_help()
        sys.exit(1)
    
    # Parse names
    names = [n.strip() for n in args.names.split(',')]
    
    # Download based on type
    if args.type == 'molecules':
        count = download_molecules(names)
        print(f"\n✅ Downloaded {count} molecules")
    elif args.type == 'drugs':
        count = download_drugs(names)
        print(f"\n✅ Downloaded {count} drugs")
    elif args.type == 'diseases':
        count = download_diseases(names, max_drugs_per_disease=args.max_drugs)
        print(f"\n✅ Processed {count} diseases")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Download interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error during download: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

