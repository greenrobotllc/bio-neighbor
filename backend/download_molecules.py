"""
CLI script to download molecules from PubChem.
Supports downloading by count or by name list.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

from rdkit import Chem
from data_loader import DB_PATH, save_to_database, load_from_database
import pandas as pd
import sqlite3


def download_molecules_by_count(count: int, source: str = "pubchem") -> pd.DataFrame:
    """
    Download molecules by count from specified source.
    
    Args:
        count: Number of molecules to download
        source: Source to use ("pubchem", "chembl", "zinc")
        
    Returns:
        DataFrame with downloaded molecules
    """
    if source == "pubchem" and not PUBCHEM_AVAILABLE:
        print("❌ PubChem not available. Install with: pip install pubchempy")
        return pd.DataFrame()
    
    print(f"📥 Downloading {count} molecules from {source}...")
    
    if source == "pubchem":
        return download_from_pubchem(count)
    elif source == "chembl":
        print("⚠️  ChEMBL download not yet implemented in this script")
        print("   Use 'python backend/main.py setup' for ChEMBL downloads")
        return pd.DataFrame()
    elif source == "zinc":
        print("⚠️  ZINC download not yet implemented in this script")
        print("   Use 'python backend/main.py setup' for ZINC downloads")
        return pd.DataFrame()
    else:
        print(f"❌ Unknown source: {source}")
        return pd.DataFrame()


def download_from_pubchem(count: int) -> pd.DataFrame:
    """
    Download molecules from PubChem.
    
    Args:
        count: Number of molecules to download
        
    Returns:
        DataFrame with molecules
    """
    molecules_data = []
    seen_cids = set()
    
    # Load existing molecules to avoid duplicates
    existing_df = load_from_database()
    if existing_df is not None and 'pubchem_cid' in existing_df.columns:
        existing_cids = set(existing_df['pubchem_cid'].dropna().astype(str))
        seen_cids.update(existing_cids)
        print(f"📊 Found {len(seen_cids)} existing molecules in database")
    
    # Common drug names to search
    drug_names = [
        "aspirin", "ibuprofen", "acetaminophen", "naproxen", "diclofenac",
        "penicillin", "amoxicillin", "azithromycin", "cephalexin", "ciprofloxacin",
        "atorvastatin", "lisinopril", "amlodipine", "metoprolol", "losartan",
        "simvastatin", "hydrochlorothiazide", "furosemide", "carvedilol", "clopidogrel",
        "metformin", "insulin", "glipizide", "pioglitazone", "sitagliptin",
        "sertraline", "escitalopram", "fluoxetine", "bupropion", "trazodone",
        "warfarin", "levothyroxine", "omeprazole", "albuterol", "gabapentin",
        "tramadol", "hydrocodone", "oxycodone", "morphine", "codeine",
        "prednisone", "tamsulosin", "fluticasone", "montelukast", "pantoprazole",
        "venlafaxine", "quetiapine", "aripiprazole", "olanzapine",
        "donepezil", "rivastigmine", "galantamine", "memantine",
        "tacrine", "physostigmine", "neostigmine"
    ]
    
    print(f"🔍 Searching PubChem for molecules...")
    
    for name in drug_names:
        if len(molecules_data) >= count:
            break
        
        try:
            compounds = pcp.get_compounds(name, 'name')
            
            for comp in compounds:
                if len(molecules_data) >= count:
                    break
                
                cid = comp.cid
                if not cid or str(cid) in seen_cids:
                    continue
                
                try:
                    smiles = comp.connectivity_smiles or comp.isomeric_smiles or getattr(comp, 'canonical_smiles', None)
                    if not smiles:
                        continue
                    
                    # Validate SMILES
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        continue
                    
                    mw = comp.molecular_weight or 0
                    
                    # Filter for drug-like molecules
                    if mw < 100 or mw > 1000:
                        continue
                    
                    name_val = comp.iupac_name
                    if not name_val and comp.synonyms:
                        name_val = comp.synonyms[0]
                    if not name_val:
                        name_val = f"PubChem_{cid}"
                    
                    molecules_data.append({
                        'chembl_id': f"PUBCHEM_{cid}",
                        'smiles': smiles,
                        'name': name_val,
                        'molecular_weight': mw,
                        'is_approved': True,
                        'targets': [],
                        'formula': comp.molecular_formula or '',
                        'inchi': '',
                        'inchikey': '',
                        'pubchem_cid': str(cid)
                    })
                    seen_cids.add(str(cid))
                    
                    if len(molecules_data) % 10 == 0:
                        print(f"  ✓ Downloaded {len(molecules_data)}/{count} molecules...")
                    
                    time.sleep(0.3)  # Rate limiting
                
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"  ⚠️  Error searching for '{name}': {e}")
            continue
    
    print(f"✅ Downloaded {len(molecules_data)} molecules from PubChem")
    
    if molecules_data:
        df = pd.DataFrame(molecules_data)
        return df
    else:
        return pd.DataFrame()


def download_molecules_by_names(names: List[str]) -> pd.DataFrame:
    """
    Download specific molecules by name list.
    
    Args:
        names: List of molecule names to download
        
    Returns:
        DataFrame with downloaded molecules
    """
    if not PUBCHEM_AVAILABLE:
        print("❌ PubChem not available. Install with: pip install pubchempy")
        return pd.DataFrame()
    
    print(f"📥 Downloading {len(names)} molecules by name from PubChem...")
    
    molecules_data = []
    seen_cids = set()
    
    # Load existing molecules
    existing_df = load_from_database()
    if existing_df is not None and 'pubchem_cid' in existing_df.columns:
        existing_cids = set(existing_df['pubchem_cid'].dropna().astype(str))
        seen_cids.update(existing_cids)
    
    for i, name in enumerate(names, 1):
        name = name.strip()
        if not name:
            continue
        
        print(f"  [{i}/{len(names)}] Searching for: {name}")
        
        try:
            compounds = pcp.get_compounds(name, 'name')
            
            if not compounds:
                print(f"    ⚠️  No compounds found for '{name}'")
                continue
            
            comp = compounds[0]  # Take first result
            cid = comp.cid
            
            if not cid or str(cid) in seen_cids:
                if str(cid) in seen_cids:
                    print(f"    ℹ️  Already exists in database (CID: {cid})")
                continue
            
            try:
                smiles = comp.connectivity_smiles or comp.isomeric_smiles or getattr(comp, 'canonical_smiles', None)
                if not smiles:
                    print(f"    ⚠️  No SMILES found for '{name}'")
                    continue
                
                # Validate SMILES
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    print(f"    ⚠️  Invalid SMILES for '{name}'")
                    continue
                
                mw = comp.molecular_weight or 0
                
                name_val = comp.iupac_name
                if not name_val and comp.synonyms:
                    name_val = comp.synonyms[0]
                if not name_val:
                    name_val = name
                
                molecules_data.append({
                    'chembl_id': f"PUBCHEM_{cid}",
                    'smiles': smiles,
                    'name': name_val,
                    'molecular_weight': mw,
                    'is_approved': True,
                    'targets': [],
                    'formula': comp.molecular_formula or '',
                    'inchi': '',
                    'inchikey': '',
                    'pubchem_cid': str(cid)
                })
                seen_cids.add(str(cid))
                print(f"    ✓ Downloaded: {name_val}")
            
            except Exception as e:
                print(f"    ⚠️  Error processing '{name}': {e}")
                continue
            
            time.sleep(0.3)  # Rate limiting
        
        except Exception as e:
            print(f"    ⚠️  Error searching for '{name}': {e}")
            continue
    
    print(f"✅ Downloaded {len(molecules_data)}/{len(names)} molecules")
    
    if molecules_data:
        df = pd.DataFrame(molecules_data)
        return df
    else:
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(
        description='Download molecules from PubChem',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download 1000 molecules
  python download_molecules.py --count 1000
  
  # Download specific molecules by name
  python download_molecules.py --names "aspirin,ibuprofen,acetaminophen"
  
  # Download from specific source
  python download_molecules.py --count 500 --source pubchem
        """
    )
    
    parser.add_argument(
        '--count',
        type=int,
        help='Number of molecules to download'
    )
    
    parser.add_argument(
        '--names',
        type=str,
        help='Comma-separated list of molecule names to download'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default='pubchem',
        choices=['pubchem', 'chembl', 'zinc'],
        help='Data source to use (default: pubchem)'
    )
    
    args = parser.parse_args()
    
    if not args.count and not args.names:
        parser.error("Either --count or --names must be specified")
    
    # Load existing database
    print("📂 Loading existing database...")
    existing_df = load_from_database()
    if existing_df is not None:
        print(f"✅ Found {len(existing_df)} existing molecules")
    else:
        print("ℹ️  No existing database found")
    
    # Download molecules
    if args.names:
        names_list = [n.strip() for n in args.names.split(',')]
        df = download_molecules_by_names(names_list)
    else:
        df = download_molecules_by_count(args.count, args.source)
    
    # Handle case where no molecules were downloaded
    if df is None or len(df) == 0:
        print("⚠️  No new molecules downloaded (may already exist in database)")
        if existing_df is not None:
            print(f"ℹ️  Current database has {len(existing_df)} molecules")
        print("=" * 60)
        print("✅ Download process completed (no new molecules)")
        print("=" * 60)
        return
    
    # Merge with existing data
    new_count = len(df)
    if existing_df is not None and len(existing_df) > 0:
        # Combine dataframes, avoiding duplicates
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        # Remove duplicates by pubchem_cid or chembl_id
        if 'pubchem_cid' in combined_df.columns:
            combined_df = combined_df.drop_duplicates(subset=['pubchem_cid'], keep='first')
        else:
            combined_df = combined_df.drop_duplicates(subset=['chembl_id'], keep='first')
        new_count = len(combined_df) - len(existing_df)
        print(f"✅ Combined with existing data: {len(combined_df)} total molecules ({new_count} new)")
        df = combined_df
    else:
        print(f"✅ Downloaded {new_count} new molecules")
    
    # Save to database
    if new_count > 0 or existing_df is None:
        print("💾 Saving to database...")
        save_to_database(df)
    
    print("\n" + "=" * 60)
    print("✅ Molecule Download Complete")
    print("=" * 60)
    print(f"Molecules in database: {len(df)}")
    if new_count == 0:
        print("ℹ️  No new molecules added (all already existed)")
    print("=" * 60)


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

