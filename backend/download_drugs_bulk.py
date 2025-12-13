"""
Bulk download drugs from PubChem.
Downloads drugs by searching for common drug names or by disease.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

from rdkit import Chem
from pubchem_drug_loader import load_drug_info, match_active_ingredients_to_molecules
from drugbank_loader import save_drugs_to_db
from data_loader import load_from_database, save_to_database, DB_PATH
from db_migrations import migrate_database


def get_drug_cids_from_pubchem_search(query: str, max_results: int = 100) -> List[int]:
    """
    Search PubChem for compounds matching a query and return CIDs.
    
    Args:
        query: Search query (e.g., "drug", "pharmaceutical", "FDA approved")
        max_results: Maximum number of results to return
        
    Returns:
        List of PubChem CIDs
    """
    if not PUBCHEM_AVAILABLE:
        return []
    
    try:
        # Search PubChem for compounds
        compounds = pcp.get_compounds(query, 'name', list_return='flat')
        cids = [c.cid for c in compounds[:max_results]]
        return cids
    except Exception as e:
        print(f"  ⚠️  Error searching PubChem: {e}")
        return []


def download_drugs_by_cid_range(start_cid: int, end_cid: int, max_drugs: int, molecule_df: Optional[pd.DataFrame] = None) -> List[Dict]:
    """
    Download drugs by iterating through PubChem CIDs.
    This is a more systematic approach for large-scale downloads.
    
    Args:
        start_cid: Starting CID
        end_cid: Ending CID
        max_drugs: Maximum number of drugs to download
        molecule_df: Optional DataFrame to match active ingredients
        
    Returns:
        List of drug information dictionaries
    """
    if not PUBCHEM_AVAILABLE:
        return []
    
    drugs = []
    checked_cids = set()
    
    print(f"🔍 Searching PubChem CIDs {start_cid} to {end_cid} for drugs...")
    
    # Search in batches to avoid rate limits
    batch_size = 10
    for batch_start in range(start_cid, min(end_cid + 1, start_cid + max_drugs * 10), batch_size):
        if len(drugs) >= max_drugs:
            break
        
        batch_end = min(batch_start + batch_size, end_cid + 1)
        
        for cid in range(batch_start, batch_end):
            if len(drugs) >= max_drugs:
                break
            
            if cid in checked_cids:
                continue
            checked_cids.add(cid)
            
            try:
                # Try to get compound
                comp = pcp.Compound.from_cid(cid)
                
                # Check if it's likely a drug (has synonyms, molecular weight in drug range, etc.)
                if comp.synonyms and len(comp.synonyms) > 0:
                    # Check if any synonym suggests it's a drug
                    synonyms_lower = [s.lower() for s in comp.synonyms[:10]]
                    is_drug_like = any(
                        any(keyword in syn for keyword in ['drug', 'pharmaceutical', 'medication', 'tablet', 'capsule', 'injection'])
                        for syn in synonyms_lower
                    ) or (
                        comp.molecular_weight and 100 <= comp.molecular_weight <= 2000  # Typical drug MW range
                    )
                    
                    if is_drug_like:
                        # Get drug name (use first reasonable synonym)
                        drug_name = comp.synonyms[0] if comp.synonyms else f"CID_{cid}"
                        
                        # Load drug info
                        drug_info = load_drug_info(drug_name, pubchem_cid=str(cid), molecule_df=molecule_df)
                        
                        if drug_info:
                            drugs.append(drug_info)
                            print(f"  ✅ Found drug: {drug_info.get('name', drug_name)} (CID: {cid})")
                
                # Rate limiting
                time.sleep(0.3)
                
            except Exception as e:
                # CID doesn't exist or error - skip
                continue
    
    return drugs


def download_drugs_bulk(max_drugs: Optional[int] = None, use_cid_search: bool = True) -> int:
    """
    Bulk download drugs from PubChem.
    
    For large downloads (1000+), uses CID range searching.
    For smaller downloads, uses common drug names.
    
    Args:
        max_drugs: Maximum number of drugs to download (None = all found)
        use_cid_search: If True and max_drugs > 100, use CID range search
        
    Returns:
        Number of drugs downloaded
    """
    if not PUBCHEM_AVAILABLE:
        print("❌ PubChem not available. Install with: pip install pubchempy")
        return 0
    
    print("=" * 60)
    print("📥 Bulk Downloading Drugs from PubChem")
    print("=" * 60)
    
    # Ensure database schema is up to date
    print("\n🔧 Checking database schema...")
    if not migrate_database():
        print("❌ Database migration failed")
        return 0
    print("✅ Database schema is up to date")
    
    # Load existing molecules for matching
    molecule_df = load_from_database()
    print(f"📊 Found {len(molecule_df) if molecule_df is not None else 0} existing molecules in database")
    
    # Determine strategy based on target count
    if max_drugs and max_drugs > 1000 and use_cid_search:
        # For large downloads, use CID range search
        print(f"🔍 Using CID range search for large-scale download ({max_drugs} drugs)...")
        print(f"   This will search PubChem compound IDs systematically")
        print(f"   Note: This may take several hours for 10,000+ drugs")
        print()
        
        # Start from CID 1 and search forward
        # PubChem has millions of compounds, but drugs are scattered
        # We'll search in ranges and filter for drug-like compounds
        start_cid = 1
        end_cid = min(1000000, start_cid + max_drugs * 100)  # Search up to 1M CIDs or enough to find target
        
        drugs = download_drugs_by_cid_range(start_cid, end_cid, max_drugs or 10000, molecule_df)
        
        # Save drugs to database
        drugs_downloaded = 0
        for drug_info in drugs:
            try:
                save_drugs_to_db([drug_info])
                drugs_downloaded += 1
            except Exception as e:
                print(f"  ⚠️  Error saving drug: {e}")
                continue
        
        print("\n" + "=" * 60)
        print(f"✅ Bulk download complete: {drugs_downloaded} drugs downloaded")
        print("=" * 60)
        
        return drugs_downloaded
    
    else:
        # For smaller downloads, use common drug names
        print(f"🔍 Using common drug names search...")
        
        # Common drug names to search (expanded list)
        common_drug_names = [
            # Pain relievers
            "aspirin", "ibuprofen", "acetaminophen", "naproxen", "diclofenac", "indomethacin",
            # Antibiotics
            "penicillin", "amoxicillin", "azithromycin", "cephalexin", "ciprofloxacin", "doxycycline",
            # Cardiovascular
            "atorvastatin", "lisinopril", "amlodipine", "metoprolol", "losartan", "simvastatin",
            "hydrochlorothiazide", "furosemide", "carvedilol", "clopidogrel", "warfarin",
            # Diabetes
            "metformin", "insulin", "glipizide", "pioglitazone", "sitagliptin", "glyburide",
            # Mental health
            "sertraline", "escitalopram", "fluoxetine", "bupropion", "trazodone", "venlafaxine",
            "quetiapine", "aripiprazole", "olanzapine", "risperidone",
            # Other common drugs
            "levothyroxine", "omeprazole", "albuterol", "gabapentin", "prednisone",
            "tamsulosin", "fluticasone", "montelukast", "pantoprazole", "duloxetine",
            # Alzheimer's drugs
            "donepezil", "rivastigmine", "galantamine", "memantine", "tacrine",
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_drug_names = []
        for name in common_drug_names:
            if name not in seen:
                seen.add(name)
                unique_drug_names.append(name)
        
        print(f"🔍 Searching for {len(unique_drug_names)} common drugs...")
        if max_drugs:
            print(f"   Target: {max_drugs} drugs")
        else:
            print(f"   Will download all found drugs")
        print()
        
        drugs_downloaded = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        for i, drug_name in enumerate(unique_drug_names, 1):
            if max_drugs and drugs_downloaded >= max_drugs:
                print(f"\n✅ Reached target of {max_drugs} drugs!")
                break
            
            # If too many consecutive errors, wait longer
            if consecutive_errors >= max_consecutive_errors:
                wait_time = min(30.0, 5.0 * consecutive_errors)
                print(f"  ⚠️  Too many consecutive errors, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                consecutive_errors = 0
            
            print(f"[{i}/{len(unique_drug_names)}] Searching for: {drug_name}")
            
            try:
                drug_info = load_drug_info(drug_name, molecule_df=molecule_df)
                
                if drug_info:
                # Save drug to database
                try:
                    save_drugs_to_db([drug_info])
                    drugs_downloaded += 1
                        print(f"  ✅ Downloaded: {drug_info.get('name', drug_name)}")
                        consecutive_errors = 0
                    except Exception as save_error:
                        print(f"  ⚠️  Error saving drug: {save_error}")
                else:
                    print(f"  ⚠️  Drug not found: {drug_name}")
                    consecutive_errors += 1
                
                # Rate limiting
                delay = 0.5 + (0.2 * consecutive_errors)
                time.sleep(min(delay, 2.0))
            
            except Exception as e:
                error_str = str(e)
                is_rate_limit = (
                    "503" in error_str or
                    "ServerBusy" in error_str or
                    "Too many requests" in error_str or
                    "PUGREST.ServerBusy" in error_str
                )
                
                if is_rate_limit:
                    consecutive_errors += 1
                    print(f"  ⚠️  Rate limited: {error_str[:80]}")
                    time.sleep(min(5.0 + (2.0 * consecutive_errors), 30.0))
                else:
                    print(f"  ⚠️  Error: {error_str[:80]}")
                    consecutive_errors += 1
                continue
        
        print("\n" + "=" * 60)
        print(f"✅ Bulk download complete: {drugs_downloaded} drugs downloaded")
        print("=" * 60)
        
        return drugs_downloaded


def main():
    parser = argparse.ArgumentParser(
        description='Bulk download drugs from PubChem',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all common drugs (no limit)
  python download_drugs_bulk.py
  
  # Download up to 100 drugs
  python download_drugs_bulk.py --max-drugs 100
        """
    )
    
    parser.add_argument(
        '--max-drugs',
        type=int,
        default=None,
        help='Maximum number of drugs to download (default: None = all found). For 1000+, uses CID range search.'
    )
    
    parser.add_argument(
        '--use-cid-search',
        action='store_true',
        default=False,
        help='Force use of CID range search (recommended for 1000+ drugs)'
    )
    
    args = parser.parse_args()
    
    if not PUBCHEM_AVAILABLE:
        print("❌ PubChem not available. Install with: pip install pubchempy")
        sys.exit(1)
    
    # Check if molecule database exists
    if not DB_PATH.exists():
        print("❌ Error: Molecules database not found.")
        print("   Please run 'python backend/main.py setup' first to create the database.")
        sys.exit(1)
    
    try:
        count = download_drugs_bulk(max_drugs=args.max_drugs, use_cid_search=args.use_cid_search or (args.max_drugs and args.max_drugs > 1000))
        sys.exit(0 if count > 0 else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Download interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error during bulk download: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

