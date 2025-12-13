"""
Bulk download drugs using RxNorm API.
RxNorm provides standardized drug names and is maintained by the National Library of Medicine.
This is ideal for getting comprehensive drug lists.

References:
- RxNorm API: https://lhncbc.nlm.nih.gov/RxNav/APIs/index.html
- RxNorm API Docs: https://lhncbc.nlm.nih.gov/RxNav/APIs/rxnorm-api.html
"""

import argparse
import sys
import time
import requests
from pathlib import Path
from typing import List, Optional, Dict
import json

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

from pubchem_drug_loader import load_drug_info
from drugbank_loader import save_drugs_to_db
from data_loader import load_from_database, DB_PATH
from db_migrations import migrate_database

# RxNorm API base URL
RXNORM_API_BASE = "https://rxnav.nlm.nih.gov/REST"


def get_all_prescribable_drugs() -> List[str]:
    """
    Get all prescribable drugs from RxNorm API.
    
    Returns:
        List of drug names (RxNorm terms)
    """
    print("🔍 Fetching all prescribable drugs from RxNorm...")
    
    try:
        # Get all prescribable names
        # RxNorm API endpoint: /allconcepts?tty=SCD (Semantic Clinical Drug)
        # or use /allconcepts?tty=BN (Brand Name) or /allconcepts?tty=IN (Ingredient)
        
        # First, try to get all ingredients (most comprehensive)
        url = f"{RXNORM_API_BASE}/allconcepts.json?tty=IN"
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            concepts = data.get('minConceptGroup', {}).get('minConcept', [])
            drug_names = [concept.get('name', '') for concept in concepts if concept.get('name')]
            print(f"✅ Found {len(drug_names)} drug ingredients from RxNorm")
            return drug_names
        
        # Fallback: try brand names
        url = f"{RXNORM_API_BASE}/allconcepts.json?tty=BN"
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            concepts = data.get('minConceptGroup', {}).get('minConcept', [])
            drug_names = [concept.get('name', '') for concept in concepts if concept.get('name')]
            print(f"✅ Found {len(drug_names)} brand names from RxNorm")
            return drug_names
        
        print("⚠️  Could not fetch from RxNorm API, using fallback list")
        return []
        
    except Exception as e:
        print(f"⚠️  Error fetching from RxNorm: {e}")
        return []


def get_drugs_by_rxcui(rxcui_list: List[str], max_drugs: Optional[int] = None) -> List[str]:
    """
    Get drug names from RxNorm CUIs (Concept Unique Identifiers).
    
    Args:
        rxcui_list: List of RxNorm CUIs
        max_drugs: Maximum number of drugs to return
        
    Returns:
        List of drug names
    """
    drug_names = []
    
    for rxcui in rxcui_list:
        if max_drugs and len(drug_names) >= max_drugs:
            break
        
        try:
            # Get properties for this RXCUI
            url = f"{RXNORM_API_BASE}/rxcui/{rxcui}/properties.json"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                properties = data.get('properties', {})
                name = properties.get('name', '')
                if name:
                    drug_names.append(name)
            
            time.sleep(0.1)  # Rate limiting
            
        except Exception as e:
            # Log occasionally to avoid spam
            # print(f"  ⚠️  Error fetching RXCUI {rxcui}: {e}")
            continue
    
    return drug_names


def search_rxnorm_drugs(query: str, max_results: int = 100) -> List[str]:
    """
    Search RxNorm for drugs matching a query.
    
    Args:
        query: Search query
        max_results: Maximum number of results
        
    Returns:
        List of drug names
    """
    try:
        url = f"{RXNORM_API_BASE}/drugs.json"
        response = requests.get(url, params={'name': query}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            drug_group = data.get('drugGroup', {})
            concept_group = drug_group.get('conceptGroup', [])
            
            drug_names = []
            for group in concept_group:
                concepts = group.get('conceptProperties', [])
                for concept in concepts[:max_results]:
                    name = concept.get('name', '')
                    if name:
                        drug_names.append(name)
            
            return drug_names[:max_results]
        
    except Exception as e:
        print(f"  ⚠️  Error searching RxNorm: {e}")
    
    return []


def download_drugs_from_rxnorm(max_drugs: Optional[int] = None, use_pubchem: bool = True) -> int:
    """
    Download drugs using RxNorm API, then fetch details from PubChem.
    
    Args:
        max_drugs: Maximum number of drugs to download
        use_pubchem: If True, fetch molecular details from PubChem
        
    Returns:
        Number of drugs downloaded
    """
    if not PUBCHEM_AVAILABLE and use_pubchem:
        print("❌ PubChem not available. Install with: pip install pubchempy")
        print("   Continuing with RxNorm names only...")
        use_pubchem = False
    
    print("=" * 60)
    print("📥 Bulk Downloading Drugs from RxNorm + PubChem")
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
    print()
    
    # Get drug names from RxNorm
    print("🔍 Step 1: Fetching drug names from RxNorm API...")
    drug_names = get_all_prescribable_drugs()
    
    if not drug_names:
        print("⚠️  Could not fetch from RxNorm, using common drug names as fallback")
        # Fallback to common drug names
        drug_names = [
            "aspirin", "ibuprofen", "acetaminophen", "naproxen", "diclofenac",
            "penicillin", "amoxicillin", "azithromycin", "cephalexin", "ciprofloxacin",
            "atorvastatin", "lisinopril", "amlodipine", "metoprolol", "losartan",
            "simvastatin", "hydrochlorothiazide", "furosemide", "carvedilol", "clopidogrel",
            "metformin", "insulin", "glipizide", "pioglitazone", "sitagliptin",
            "sertraline", "escitalopram", "fluoxetine", "bupropion", "trazodone",
            "warfarin", "levothyroxine", "omeprazole", "albuterol", "gabapentin",
            "donepezil", "rivastigmine", "galantamine", "memantine"
        ]
    
    # Limit to max_drugs if specified
    if max_drugs:
        drug_names = drug_names[:max_drugs]
        print(f"📊 Limited to {max_drugs} drugs")
    
    print(f"✅ Found {len(drug_names)} drugs to process")
    print()
    
    # Step 2: Fetch drug details from PubChem
    if use_pubchem:
        print("🔍 Step 2: Fetching drug details from PubChem...")
        print(f"   This may take a while for {len(drug_names)} drugs...")
        print()
    else:
        print("⚠️  Skipping PubChem - will only store RxNorm names")
        print()
    
    drugs_downloaded = 0
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    for i, drug_name in enumerate(drug_names, 1):
        # Progress update every 10 drugs
        if i % 10 == 0:
            print(f"Progress: {i}/{len(drug_names)} ({drugs_downloaded} downloaded)")
        
        # If too many consecutive errors, wait longer
        if consecutive_errors >= max_consecutive_errors:
            wait_time = min(30.0, 5.0 * consecutive_errors)
            print(f"  ⚠️  Too many consecutive errors, waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            consecutive_errors = 0
        
        try:
            if use_pubchem:
                # Fetch full drug info from PubChem
                drug_info = load_drug_info(drug_name, molecule_df=molecule_df)
            else:
                # Create minimal drug info from RxNorm name only
                drug_info = {
                    'name': drug_name,
                    'generic_name': drug_name,
                    'pubchem_cid': None,
                    'description': f"Drug from RxNorm: {drug_name}",
                    'indication': None,
                    'active_ingredients': [],
                    'inactive_ingredients': [],
                    'smiles': None,
                    'molecular_weight': 0
                }
            
            if drug_info:
                # Save drug to database
                try:
                    save_drugs_to_db([drug_info])
                    drugs_downloaded += 1
                    if i % 10 == 0:  # Only print every 10th to avoid spam
                        print(f"  ✅ Downloaded: {drug_info.get('name', drug_name)}")
                    consecutive_errors = 0
                except Exception as save_error:
                    if i % 10 == 0:
                        print(f"  ⚠️  Error saving drug: {save_error}")
            else:
                consecutive_errors += 1
            
            # Rate limiting
            delay = 0.3 if use_pubchem else 0.1
            time.sleep(delay)
        
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
                if i % 10 == 0:
                    print(f"  ⚠️  Rate limited: {error_str[:80]}")
                time.sleep(min(5.0 + (2.0 * consecutive_errors), 30.0))
            else:
                consecutive_errors += 1
            continue
    
    print("\n" + "=" * 60)
    print(f"✅ Bulk download complete: {drugs_downloaded} drugs downloaded")
    print("=" * 60)
    
    return drugs_downloaded


def main():
    parser = argparse.ArgumentParser(
        description='Bulk download drugs using RxNorm API + PubChem',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all prescribable drugs from RxNorm (with PubChem details)
  python download_drugs_rxnorm.py --max-drugs 10000
  
  # Download without PubChem (faster, RxNorm names only)
  python download_drugs_rxnorm.py --max-drugs 10000 --no-pubchem

References:
- RxNorm API: https://lhncbc.nlm.nih.gov/RxNav/APIs/index.html
- RxNorm provides standardized drug names from the National Library of Medicine
        """
    )
    
    parser.add_argument(
        '--max-drugs',
        type=int,
        default=None,
        help='Maximum number of drugs to download (default: None = all from RxNorm)'
    )
    
    parser.add_argument(
        '--no-pubchem',
        action='store_true',
        help='Skip PubChem lookup (faster, but only stores RxNorm names)'
    )
    
    args = parser.parse_args()
    
    # Check if molecule database exists
    if not DB_PATH.exists():
        print("❌ Error: Molecules database not found.")
        print("   Please run 'python backend/main.py setup' first to create the database.")
        sys.exit(1)
    
    try:
        count = download_drugs_from_rxnorm(
            max_drugs=args.max_drugs,
            use_pubchem=not args.no_pubchem
        )
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

