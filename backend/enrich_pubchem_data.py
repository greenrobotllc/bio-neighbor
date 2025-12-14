#!/usr/bin/env python3
"""
Enrich PubChem data using PubChem REST API.
For molecules with missing names or other metadata, query PubChem API to fill in the gaps.

Usage:
    python enrich_pubchem_data.py [--update-db] [--max-molecules 1000] [--batch-size 10]
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional
import sqlite3
import pandas as pd

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

# Import data_loader functions
from data_loader import DB_PATH, load_from_database, save_to_database

def extract_pubchem_cid(chembl_id: str, pubchem_cid: str = "") -> Optional[int]:
    """
    Extract PubChem CID from chembl_id or pubchem_cid column.
    
    Args:
        chembl_id: ChEMBL ID (may be PUBCHEM_<cid> format or numeric)
        pubchem_cid: PubChem CID from database column
        
    Returns:
        PubChem CID as integer, or None if not a PubChem compound
    """
    # First check pubchem_cid column
    if pubchem_cid and str(pubchem_cid).strip():
        try:
            return int(str(pubchem_cid).strip())
        except ValueError:
            pass
    
    # Check if chembl_id has PUBCHEM_ prefix
    if chembl_id and str(chembl_id).startswith("PUBCHEM_"):
        try:
            cid_str = str(chembl_id).replace("PUBCHEM_", "").strip()
            return int(cid_str)
        except ValueError:
            pass
    
    # Check if chembl_id is purely numeric (might be a PubChem CID)
    # But be conservative - only if it looks like a valid CID (reasonable range)
    if chembl_id and str(chembl_id).strip().isdigit():
        try:
            cid = int(str(chembl_id).strip())
            # PubChem CIDs are typically in a reasonable range (1 to ~100 million)
            if 1 <= cid <= 100000000:
                return cid
        except ValueError:
            pass
    
    return None

def enrich_molecule_from_pubchem(cid: int) -> Optional[Dict]:
    """
    Enrich molecule data from PubChem API.
    
    Args:
        cid: PubChem Compound ID
        
    Returns:
        Dictionary with enriched data, or None if not found
    """
    if not PUBCHEM_AVAILABLE:
        return None
    
    try:
        compound = pcp.Compound.from_cid(cid)
        
        # Get name (prioritize IUPAC, then preferred name, then first synonym)
        name = ""
        if compound.iupac_name:
            name = compound.iupac_name
        elif hasattr(compound, 'preferred_name') and compound.preferred_name:
            name = compound.preferred_name
        elif compound.synonyms:
            name = compound.synonyms[0]
        
        # Get molecular formula
        formula = compound.molecular_formula or ""
        
        # Get InChI
        inchi = compound.inchi or ""
        
        # Get InChIKey
        inchikey = compound.inchikey or ""
        
        return {
            'name': name,
            'formula': formula,
            'inchi': inchi,
            'inchikey': inchikey,
            'pubchem_cid': str(cid)
        }
    except Exception as e:
        print(f"  ⚠️  Error fetching CID {cid}: {e}")
        return None

def enrich_molecules(df: pd.DataFrame, max_molecules: Optional[int] = None, 
                     batch_size: int = 10, update_db: bool = False) -> pd.DataFrame:
    """
    Enrich molecules with missing data using PubChem API.
    
    Args:
        df: DataFrame with molecules
        max_molecules: Maximum number of molecules to enrich (None = all)
        batch_size: Number of molecules to process before saving progress
        update_db: If True, update database after enrichment
        
    Returns:
        Enriched DataFrame
    """
    if not PUBCHEM_AVAILABLE:
        print("❌ Error: pubchempy is not installed. Install with: pip install pubchempy")
        return df
    
    print(f"🔍 Enriching molecules with PubChem data...")
    print(f"   Total molecules: {len(df)}")
    
    # Find molecules that need enrichment (PubChem compounds with missing names)
    # Skip molecules that already have names to avoid re-processing
    needs_enrichment = []
    for idx, row in df.iterrows():
        cid = extract_pubchem_cid(
            row.get('chembl_id', ''),
            row.get('pubchem_cid', '')
        )
        if cid:
            # Check if name is missing or empty
            name = str(row.get('name', '')).strip()
            if not name or name == '':
                needs_enrichment.append((idx, cid, row))
    
    print(f"   Found {len(needs_enrichment)} PubChem molecules needing enrichment")
    
    if max_molecules:
        needs_enrichment = needs_enrichment[:max_molecules]
        print(f"   Limiting to {max_molecules} molecules")
    
    if not needs_enrichment:
        print("✅ No molecules need enrichment")
        return df
    
    # Enrich molecules
    enriched_count = 0
    df_enriched = df.copy()
    
    for i, (idx, cid, row) in enumerate(needs_enrichment):
        if (i + 1) % 10 == 0:
            print(f"  ✓ Processing {i + 1}/{len(needs_enrichment)}...")
        
        # Fetch data from PubChem
        enriched_data = enrich_molecule_from_pubchem(cid)
        
        if enriched_data:
            # Update DataFrame
            for key, value in enriched_data.items():
                if key in df_enriched.columns:
                    df_enriched.at[idx, key] = value
            enriched_count += 1
        
        # Rate limiting - be nice to PubChem API
        time.sleep(0.1)
        
        # Save progress periodically
        if update_db and (i + 1) % batch_size == 0:
            print(f"  💾 Saving progress ({i + 1} molecules processed)...")
            try:
                save_to_database(df_enriched, timeout=60.0)
            except Exception as e:
                print(f"  ⚠️  Warning: Could not save progress: {e}")
                print(f"  Continuing enrichment... (progress will be saved at end)")
    
    print(f"✅ Enriched {enriched_count}/{len(needs_enrichment)} molecules")
    
    # Final save if requested
    if update_db:
        print("💾 Saving enriched data to database...")
        try:
            save_to_database(df_enriched, timeout=60.0)
        except Exception as e:
            print(f"  ⚠️  Warning: Could not save to database: {e}")
            print(f"  You may need to close any programs accessing the database and run again")
            print(f"  Progress: {enriched_count} molecules enriched in memory")
    
    return df_enriched

def main():
    parser = argparse.ArgumentParser(
        description="Enrich PubChem data using PubChem REST API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enrich up to 100 molecules and update database
  python enrich_pubchem_data.py --update-db --max-molecules 100

  # Enrich all molecules but don't update database (dry run)
  python enrich_pubchem_data.py --max-molecules 1000

  # Enrich with custom batch size
  python enrich_pubchem_data.py --update-db --batch-size 50
        """
    )
    
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="Update database with enriched data"
    )
    parser.add_argument(
        "--max-molecules",
        type=int,
        default=None,
        help="Maximum number of molecules to enrich (default: all)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of molecules to process before saving progress (default: 10)"
    )
    
    args = parser.parse_args()
    
    if not PUBCHEM_AVAILABLE:
        print("❌ Error: pubchempy is not installed")
        print("   Install with: pip install pubchempy")
        sys.exit(1)
    
    print("🚀 PubChem Data Enrichment")
    print("=" * 60)
    print(f"Update database: {args.update_db}")
    print(f"Max molecules: {args.max_molecules or 'all'}")
    print(f"Batch size: {args.batch_size}")
    print("=" * 60 + "\n")
    
    # Load molecules from database
    df = load_from_database()
    if df is None:
        print("❌ Error: No molecule database found")
        print("   Please run: python backend/main.py setup")
        sys.exit(1)
    
    # Enrich molecules
    df_enriched = enrich_molecules(
        df, 
        max_molecules=args.max_molecules,
        batch_size=args.batch_size,
        update_db=args.update_db
    )
    
    # Show summary
    print("\n📊 Enrichment Summary:")
    print(f"   Total molecules: {len(df_enriched)}")
    print(f"   Molecules with names: {df_enriched['name'].str.strip().ne('').sum()}")
    print(f"   Molecules with formulas: {df_enriched['formula'].str.strip().ne('').sum()}")
    print(f"   Molecules with InChI: {df_enriched['inchi'].str.strip().ne('').sum()}")
    print(f"   Molecules with InChIKey: {df_enriched['inchikey'].str.strip().ne('').sum()}")
    
    if not args.update_db:
        print("\n💡 Note: Database was not updated (dry run mode)")
        print("   Use --update-db to save changes")

if __name__ == "__main__":
    main()

