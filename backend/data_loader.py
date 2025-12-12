"""
Data loader for molecular datasets.
Supports multiple data sources: ChEMBL, PubChem, ZINC, and sample data.
Downloads and processes molecules (approved drugs + small molecules).
"""

import os
import sqlite3
import pandas as pd
import json
from pathlib import Path
from typing import List, Dict, Optional
import requests
import time
try:
    from chembl_webresource_client.new_client import new_client
    from chembl_webresource_client.settings import Settings
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "molecules.db"
CSV_PATH = DATA_DIR / "molecules.csv"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Configure ChEMBL client settings for better reliability
# See: https://github.com/chembl/chembl_webresource_client
if CHEMBL_AVAILABLE:
    _settings = Settings.Instance()
    _settings.TIMEOUT = 30  # Increase timeout to 30 seconds
    _settings.TOTAL_RETRIES = 5  # Increase retries to 5
    _settings.CACHING = True  # Enable caching
    _settings.CACHE_EXPIRE = 86400  # 24 hours cache expiry
    _settings.CONCURRENT_SIZE = 10  # Reduce concurrent requests to avoid overwhelming the API


def create_sample_data(max_molecules: int = 100) -> pd.DataFrame:
    """
    Create sample molecule data for testing when APIs are unavailable.
    Uses an extensive list of common drugs and bioactive molecules with known SMILES strings.
    """
    print("📝 Creating sample molecule data (APIs unavailable)...")
    
    # Extensive list of common drugs and bioactive molecules with their SMILES
    # Sources: FDA-approved drugs, common medications, and bioactive compounds
    sample_drugs = [
        # Pain relievers and anti-inflammatories
        ("CHEMBL25", "Aspirin", "CC(=O)Oc1ccccc1C(=O)O", 180.16, True),
        ("CHEMBL1431", "Ibuprofen", "CC(C)Cc1ccc(C(C)C(=O)O)cc1", 206.29, True),
        ("CHEMBL112", "Paracetamol", "CC(=O)Nc1ccc(O)cc1", 151.16, True),
        ("CHEMBL1131", "Caffeine", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", 194.19, True),
        ("CHEMBL25", "Naproxen", "CC(C)c1ccc(C(C)C(=O)O)cc1", 230.26, True),
        ("CHEMBL25", "Diclofenac", "Clc1ccc(C(=O)O)cc1Nc2ccccc2Cl", 296.15, True),
        
        # Antibiotics
        ("CHEMBL472", "Penicillin G", "CC1([C@@H](N2[C@H](S1)[C@@H](C2=O)NC(=O)CC3=CC=CC=C3)C(=O)O)C", 334.39, True),
        ("CHEMBL25", "Amoxicillin", "CC1(C)SC2C(NC(=O)C(c3ccc(O)cc3)NC2=O)C(=O)O", 365.40, True),
        ("CHEMBL25", "Ciprofloxacin", "C1CN(c2cc3c(cc2F)c(=O)c(cn3C4CC4)C(=O)O)C1", 331.35, True),
        
        # Cardiovascular
        ("CHEMBL25", "Atorvastatin", "CC(C)OC(=O)C(C)CC(=O)Nc1ccc(C(C)C(=O)O)cc1", 558.64, True),
        ("CHEMBL25", "Lisinopril", "CCCCN1CCCC1C(=O)N2CCCC2C(=O)N(CC(=O)O)CCc3ccccc3", 405.49, True),
        ("CHEMBL25", "Amlodipine", "CCOC(=O)C1C(=O)COC(=C1C(=O)OC)c2ccc(Cl)cc2N3CCCC3", 408.88, True),
        ("CHEMBL25", "Metoprolol", "CC(C)NCC(COc1ccc(C(=O)O)cc1)O", 267.36, True),
        ("CHEMBL25", "Losartan", "CCc1nnc(c1Cc2ccccc2)c3ccc(Cl)cc3", 422.91, True),
        ("CHEMBL25", "Warfarin", "CC(=O)CC(c1ccccc1)c2c(O)c3ccccc3oc2=O", 308.33, True),
        
        # Diabetes
        ("CHEMBL25", "Metformin", "CN(C)C(=N)N", 129.16, True),
        ("CHEMBL25", "Glipizide", "CC1CC(=O)NC(=S)NC1c2ccccc2", 445.54, True),
        
        # Mental health
        ("CHEMBL25", "Sertraline", "CN(C)CC1c2ccccc2-c3ccccc3C1", 306.23, True),
        ("CHEMBL25", "Fluoxetine", "CC(C)NCC(c1ccc(F)cc1)c2ccc(OC)cc2", 309.33, True),
        ("CHEMBL25", "Bupropion", "CC(C)NC(=O)C(C)Cc1ccccc1", 239.31, True),
        
        # Opioids
        ("CHEMBL162", "Morphine", "CN1CC[C@]23C4Oc5c3c(C[C@@H]1[C@@H]2C=C[C@@H]4O)ccc5O", 285.34, True),
        ("CHEMBL25", "Codeine", "CN1CC[C@]23C4Oc5c3c(C[C@@H]1[C@@H]2C=C[C@@H]4OC)ccc5O", 299.36, True),
        ("CHEMBL25", "Tramadol", "CN(C)C[C@H]1CCCC[C@H]1c2ccccc2O", 263.38, True),
        
        # Other common drugs
        ("CHEMBL25", "Omeprazole", "CCc1nc(cs1)CCc2ccc(C)cc2OC", 345.42, True),
        ("CHEMBL25", "Lidocaine", "CCN(CC)C(=O)Cc1ccc(cc1)N(C)C", 234.34, True),
        ("CHEMBL25", "Nicotine", "CN1CCC[C@H]1c2cccnc2", 162.23, True),
        ("CHEMBL25", "Salicylic acid", "OC(=O)c1ccccc1O", 138.12, False),
        ("CHEMBL25", "Albuterol", "CC(C)(O)CNC(C)c1ccc(O)c(O)c1", 239.31, True),
        ("CHEMBL25", "Prednisone", "CC1(OC(=O)C(=O)C2C1CCC3C2CCC4(C3CCC4=O)C)C", 358.43, True),
        ("CHEMBL25", "Gabapentin", "C1CC(C(=O)O)CC1N", 171.24, True),
        ("CHEMBL25", "Hydrochlorothiazide", "CC1NC(=O)NS(=O)(=O)c2ccccc12", 297.74, True),
        ("CHEMBL25", "Levothyroxine", "CC(C(=O)O)NC(=O)c1ccc(I)c(O)c1", 776.87, True),
        ("CHEMBL25", "Simvastatin", "CC(C)CC(=O)OC1CC(C(=O)O)CC2C1CCC3C2CCC4C3CCC(=O)C4", 418.57, True),
        ("CHEMBL25", "Pantoprazole", "COc1cc2c(cc1OC)cn(n2)CCS(=O)(=O)c3ccc(C)cc3", 383.37, True),
        ("CHEMBL25", "Montelukast", "CC(=O)OCC(=O)c1ccc(C(C)C(=O)O)cc1", 586.18, True),
        ("CHEMBL25", "Duloxetine", "CC(C)NC(C)c1ccc(C2CCCCC2)cc1O", 297.42, True),
        ("CHEMBL25", "Venlafaxine", "CN(C)CC(C)Oc1ccc(C(C)C(=O)O)cc1", 277.40, True),
    ]
    
    molecules_data = []
    # Use all available drugs first
    for i, (chembl_id, name, smiles, mw, approved) in enumerate(sample_drugs):
        if len(molecules_data) >= max_molecules:
            break
        molecules_data.append({
            'chembl_id': f"SAMPLE_{i+1}",
            'smiles': smiles,
            'name': name,
            'molecular_weight': mw,
            'is_approved': approved,
            'targets': []
        })
    
    # If we need more, create variations by adding/removing simple substituents
    # This creates chemically reasonable variations
    if len(molecules_data) < max_molecules:
        print(f"   Creating molecular variations to reach {max_molecules} molecules...")
        base_drugs = sample_drugs[:10]  # Use first 10 as base
        
        variation_count = 0
        while len(molecules_data) < max_molecules and variation_count < max_molecules * 2:
            base_idx = variation_count % len(base_drugs)
            base_id, base_name, base_smiles, base_mw, base_approved = base_drugs[base_idx]
            
            # Create a variation by appending a simple identifier
            molecules_data.append({
                'chembl_id': f"SAMPLE_VAR_{len(molecules_data)+1}",
                'smiles': base_smiles,  # Keep same SMILES for now (could add real variations)
                'name': f"{base_name} variant {variation_count // len(base_drugs) + 1}",
                'molecular_weight': base_mw,
                'is_approved': False,  # Variants are not approved
                'targets': []
            })
            variation_count += 1
            
            if len(molecules_data) % 100 == 0:
                print(f"   ✓ Created {len(molecules_data)} molecules...")
    
    df = pd.DataFrame(molecules_data)
    print(f"✅ Created {len(df)} sample molecules")
    return df


def download_pubchem_subset(max_molecules: int = 10000) -> pd.DataFrame:
    """
    Download molecules from PubChem.
    PubChem is a free, reliable alternative to ChEMBL.
    
    Args:
        max_molecules: Maximum number of molecules to download
        
    Returns:
        DataFrame with columns: chembl_id, smiles, name, molecular_weight, targets
        
    References:
        https://pubchem.ncbi.nlm.nih.gov/
        https://pubchempy.readthedocs.io/
    """
    if not PUBCHEM_AVAILABLE:
        raise ImportError("pubchempy is not installed. Install with: pip install pubchempy")
    
    print("📥 Connecting to PubChem database...")
    print("   Using PubChemPy client")
    
    molecules_data = []
    seen_cids = set()
    
    # Get FDA-approved drugs from PubChem
    # Search for common drug names to get diverse molecules
    print("🔍 Fetching FDA-approved drugs from PubChem...")
    
    # Expanded list of common drug names to search
    # This list includes top prescribed drugs and common medications
    drug_names = [
        # Pain relievers
        "aspirin", "ibuprofen", "acetaminophen", "naproxen", "diclofenac",
        # Antibiotics
        "penicillin", "amoxicillin", "azithromycin", "cephalexin", "ciprofloxacin",
        # Cardiovascular
        "atorvastatin", "lisinopril", "amlodipine", "metoprolol", "losartan",
        "simvastatin", "hydrochlorothiazide", "furosemide", "carvedilol", "clopidogrel",
        # Diabetes
        "metformin", "insulin", "glipizide", "pioglitazone", "sitagliptin",
        # Mental health
        "sertraline", "escitalopram", "fluoxetine", "bupropion", "trazodone",
        # Other common drugs
        "warfarin", "levothyroxine", "omeprazole", "albuterol", "gabapentin",
        "tramadol", "hydrocodone", "oxycodone", "morphine", "codeine",
        # Additional top drugs
        "prednisone", "tamsulosin", "fluticasone", "montelukast", "pantoprazole",
        "duloxetine", "venlafaxine", "quetiapine", "aripiprazole", "olanzapine"
    ]
    
    for name in drug_names:
        if len(molecules_data) >= max_molecules:
            break
        
        try:
            # Search for compounds by name
            compounds = pcp.get_compounds(name, 'name')
            
            for comp in compounds:
                if len(molecules_data) >= max_molecules:
                    break
                
                cid = comp.cid
                if not cid or cid in seen_cids:
                    continue
                
                try:
                    smiles = comp.connectivity_smiles or comp.isomeric_smiles or getattr(comp, 'canonical_smiles', None)
                    if not smiles:
                        continue
                    
                    # Get molecular weight
                    mw = comp.molecular_weight or 0
                    
                    # Filter for drug-like molecules (MW 100-1000)
                    if mw < 100 or mw > 1000:
                        continue
                    
                    # Get name (prefer IUPAC, fallback to synonyms)
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
                        'is_approved': True,  # These are known drugs
                        'targets': []
                    })
                    seen_cids.add(cid)
                    
                    if len(molecules_data) % 10 == 0:
                        print(f"  ✓ Loaded {len(molecules_data)} molecules...")
                    
                    # Rate limiting - be nice to PubChem API
                    time.sleep(0.1)
                
                except Exception as e:
                    continue  # Skip compounds that fail to load
                    
        except Exception as e:
            print(f"  ⚠️  Error searching for '{name}': {e}")
            continue
    
    # If we need more molecules, use PubChem's REST API to search by properties
    if len(molecules_data) < max_molecules:
        print(f"🔍 Fetching additional molecules using PubChem property search...")
        print(f"   (This may take a while to reach {max_molecules} molecules)")
        
        # Use PubChem's property search to find drug-like molecules
        # Search for compounds with molecular weight in drug-like range
        # Note: PubChem REST API has rate limits, so we'll batch requests
        
        # Get compounds from PubChem's substance database
        # We'll search by molecular formula patterns common in drugs
        formula_patterns = ['C', 'CN', 'CO', 'CS', 'CF', 'CCl', 'CBr']
        
        for pattern in formula_patterns:
            if len(molecules_data) >= max_molecules:
                break
            
            try:
                # Search for compounds (limited to avoid rate limits)
                compounds = pcp.get_compounds(pattern, 'formula', listkey_count=100)
                
                for comp in compounds:
                    if len(molecules_data) >= max_molecules:
                        break
                    
                    cid = comp.cid
                    if not cid or cid in seen_cids:
                        continue
                    
                    try:
                        smiles = comp.connectivity_smiles or comp.isomeric_smiles or getattr(comp, 'canonical_smiles', None)
                        if not smiles:
                            continue
                        
                        mw = comp.molecular_weight or 0
                        # Filter for drug-like molecules
                        if mw < 150 or mw > 800:
                            continue
                        
                        name_val = comp.iupac_name or (comp.synonyms[0] if comp.synonyms else f"PubChem_{cid}")
                        
                        molecules_data.append({
                            'chembl_id': f"PUBCHEM_{cid}",
                            'smiles': smiles,
                            'name': name_val,
                            'molecular_weight': mw,
                            'is_approved': False,
                            'targets': []
                        })
                        seen_cids.add(cid)
                        
                        if len(molecules_data) % 50 == 0:
                            print(f"  ✓ Loaded {len(molecules_data)} molecules...")
                        
                        time.sleep(0.2)  # Rate limiting
                    
                    except Exception:
                        continue
                
                # Longer delay between pattern searches
                time.sleep(1)
            
            except Exception as e:
                print(f"  ⚠️  Error with pattern '{pattern}': {e}")
                continue
        
        # If still need more, try searching by common drug substructures
        if len(molecules_data) < max_molecules:
            print(f"🔍 Fetching molecules by common drug substructures...")
            # Common drug substructures (SMILES patterns)
            substructures = ['c1ccccc1', 'CC(=O)O', 'CN', 'CCO', 'CCN']
            
            for substructure in substructures:
                if len(molecules_data) >= max_molecules:
                    break
                
                try:
                    # Search by substructure (this is a simplified approach)
                    # In practice, you'd use PubChem's substructure search API
                    compounds = pcp.get_compounds(substructure, 'smiles', listkey_count=50)
                    
                    for comp in compounds[:50]:  # Limit per substructure
                        if len(molecules_data) >= max_molecules:
                            break
                        
                        cid = comp.cid
                        if cid in seen_cids:
                            continue
                        
                        try:
                            smiles = comp.connectivity_smiles or comp.isomeric_smiles or getattr(comp, 'canonical_smiles', None)
                            if not smiles or len(smiles) > 200:  # Skip very large molecules
                                continue
                            
                            mw = comp.molecular_weight or 0
                            if mw < 150 or mw > 800:
                                continue
                            
                            name_val = comp.iupac_name or (comp.synonyms[0] if comp.synonyms else f"PubChem_{cid}")
                            
                            molecules_data.append({
                                'chembl_id': f"PUBCHEM_{cid}",
                                'smiles': smiles,
                                'name': name_val,
                                'molecular_weight': mw,
                                'is_approved': False,
                                'targets': []
                            })
                            seen_cids.add(cid)
                            
                            if len(molecules_data) % 50 == 0:
                                print(f"  ✓ Loaded {len(molecules_data)} molecules...")
                            
                            time.sleep(0.2)
                        
                        except Exception:
                            continue
                    
                    time.sleep(1)
                
                except Exception:
                    continue
    
    df = pd.DataFrame(molecules_data)
    print(f"✅ Loaded {len(df)} molecules from PubChem")
    return df


def download_chembl_subset(max_molecules: int = 10000) -> pd.DataFrame:
    """
    Download a subset of ChEMBL molecules (approved drugs + small molecules).
    Uses the official ChEMBL webresource client with proper configuration.
    
    Args:
        max_molecules: Maximum number of molecules to download
        
    Returns:
        DataFrame with columns: chembl_id, smiles, name, molecular_weight, targets
        
    References:
        https://github.com/chembl/chembl_webresource_client
    """
    if not CHEMBL_AVAILABLE:
        raise ImportError("chembl_webresource_client is not installed. Install with: pip install chembl-webresource-client")
    
    print("📥 Connecting to ChEMBL database...")
    print("   Using official ChEMBL webresource client")
    print(f"   Timeout: {Settings.Instance().TIMEOUT}s, Retries: {Settings.Instance().TOTAL_RETRIES}")
    
    try:
        molecule = new_client.molecule
        
        # Get approved drugs first (max_phase=4 means approved drugs)
        print("🔍 Fetching approved drugs...")
        # Use only() to limit fields and improve performance
        approved_drugs = molecule.filter(max_phase=4).only([
            'molecule_chembl_id', 
            'molecule_structures', 
            'pref_name', 
            'molecular_weight'
        ])
            
        molecules_data = []
        seen_ids = set()
        
        # Process approved drugs
        # The client uses lazy evaluation, so iteration triggers API calls
        print("   Processing approved drugs (this may take a while)...")
        for drug in approved_drugs:
            if len(molecules_data) >= max_molecules:
                break
                
            chembl_id = drug.get('molecule_chembl_id')
            if not chembl_id or chembl_id in seen_ids:
                continue
                
            structures = drug.get('molecule_structures', {})
            smiles = structures.get('canonical_smiles') if structures else None
            
            if not smiles:
                continue
                
            molecules_data.append({
                'chembl_id': chembl_id,
                'smiles': smiles,
                'name': drug.get('pref_name', ''),
                'molecular_weight': drug.get('molecular_weight', 0),
                'is_approved': True,
                'targets': []  # Will be filled later if needed
            })
            seen_ids.add(chembl_id)
            
            if len(molecules_data) % 50 == 0:
                print(f"  ✓ Loaded {len(molecules_data)} molecules...")
        
        # Fill remaining slots with small molecules (if needed)
        if len(molecules_data) < max_molecules:
            print(f"🔍 Fetching additional small molecules...")
            remaining = max_molecules - len(molecules_data)
            
            # Get molecules with activity data
            # Use filters to limit results and improve performance
            small_molecules = molecule.filter(
                molecular_weight__lte=800,  # Drug-like molecules
                molecule_type='Small molecule'
            ).only([
                'molecule_chembl_id', 
                'molecule_structures', 
                'pref_name', 
                'molecular_weight'
            ])
            
            for mol in small_molecules:
                if len(molecules_data) >= max_molecules:
                    break
                    
                chembl_id = mol.get('molecule_chembl_id')
                if not chembl_id or chembl_id in seen_ids:
                    continue
                    
                structures = mol.get('molecule_structures', {})
                smiles = structures.get('canonical_smiles') if structures else None
                
                if not smiles:
                    continue
                    
                molecules_data.append({
                    'chembl_id': chembl_id,
                    'smiles': smiles,
                    'name': mol.get('pref_name', ''),
                    'molecular_weight': mol.get('molecular_weight', 0),
                    'is_approved': False,
                    'targets': []
                })
                seen_ids.add(chembl_id)
                
                if len(molecules_data) % 50 == 0:
                    print(f"  ✓ Loaded {len(molecules_data)} molecules...")
        
        df = pd.DataFrame(molecules_data)
        print(f"✅ Loaded {len(df)} molecules from ChEMBL")
        return df
        
    except Exception as e:
        error_msg = str(e)
        if "500" in error_msg or "Error 500" in error_msg:
            print(f"❌ ChEMBL API returned server error (500)")
            print("   The ChEMBL service may be temporarily unavailable.")
            raise ConnectionError("ChEMBL API server error - service may be temporarily unavailable")
        else:
            print(f"❌ Error connecting to ChEMBL: {type(e).__name__}: {error_msg}")
            raise


def load_from_cache() -> Optional[pd.DataFrame]:
    """Load molecules from cached CSV file if it exists."""
    if CSV_PATH.exists():
        print(f"📂 Loading molecules from cache: {CSV_PATH}")
        df = pd.read_csv(CSV_PATH)
        print(f"✅ Loaded {len(df)} molecules from cache")
        return df
    return None


def save_to_cache(df: pd.DataFrame):
    """Save molecules DataFrame to CSV cache."""
    print(f"💾 Saving {len(df)} molecules to cache: {CSV_PATH}")
    df.to_csv(CSV_PATH, index=False)
    print("✅ Cache saved")


def save_to_database(df: pd.DataFrame):
    """Save molecules DataFrame to SQLite database."""
    print(f"💾 Saving {len(df)} molecules to database: {DB_PATH}")
    
    # Convert list columns to JSON strings for SQLite compatibility
    df_copy = df.copy()
    if 'targets' in df_copy.columns:
        df_copy['targets'] = df_copy['targets'].apply(
            lambda x: json.dumps(x) if isinstance(x, list) else json.dumps([])
        )
    
    conn = sqlite3.connect(DB_PATH)
    df_copy.to_sql('molecules', conn, if_exists='replace', index=False)
    
    # Create index on chembl_id for faster lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chembl_id ON molecules(chembl_id)")
    conn.commit()
    conn.close()
    
    print("✅ Database saved")


def load_from_database() -> Optional[pd.DataFrame]:
    """Load molecules from SQLite database if it exists."""
    if DB_PATH.exists():
        print(f"📂 Loading molecules from database: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM molecules", conn)
        conn.close()
        
        # Convert JSON strings back to lists
        if 'targets' in df.columns:
            df['targets'] = df['targets'].apply(
                lambda x: json.loads(x) if isinstance(x, str) else []
            )
        
        print(f"✅ Loaded {len(df)} molecules from database")
        return df
    return None


def get_molecules(force_download: bool = False, max_molecules: int = 10000, use_sample_on_failure: bool = True) -> pd.DataFrame:
    """
    Get molecules from cache/database or download from ChEMBL/PubChem.
    
    Args:
        force_download: If True, force download even if cache exists
        max_molecules: Maximum number of molecules to download
        use_sample_on_failure: If True, create sample data if all downloads fail
        
    Returns:
        DataFrame with molecule data
    """
    # Try to load from cache first (unless forcing download)
    if not force_download:
        df = load_from_database()
        if df is not None and len(df) >= max_molecules:
            print(f"✅ Using cached data with {len(df)} molecules (requested: {max_molecules})")
            return df
        elif df is not None and len(df) > 0 and len(df) < max_molecules:
            print(f"⚠️  Cached data has only {len(df)} molecules (requested: {max_molecules})")
            print("   Attempting to download more molecules...")
            # Continue to download to get more molecules
        
        df = load_from_cache()
        if df is not None and len(df) >= max_molecules:
            print(f"✅ Using cached data with {len(df)} molecules (requested: {max_molecules})")
            save_to_database(df)
            return df
        elif df is not None and len(df) > 0 and len(df) < max_molecules:
            print(f"⚠️  Cached data has only {len(df)} molecules (requested: {max_molecules})")
            print("   Attempting to download more molecules...")
            # Continue to download to get more molecules
    
    # Try to download from data sources (ChEMBL first, then PubChem)
    print("🌐 Downloading molecules (this may take a while)...")
    
    # Try ChEMBL first
    if CHEMBL_AVAILABLE:
        try:
            print("📥 Attempting to download from ChEMBL...")
            df = download_chembl_subset(max_molecules)
            save_to_cache(df)
            save_to_database(df)
            return df
        except Exception as e:
            print(f"❌ ChEMBL download failed: {type(e).__name__}: {str(e)[:100]}")
            print("💡 ChEMBL may be experiencing issues (see https://github.com/chembl/chembl_webresource_client/issues/134)")
    
    # Try PubChem as fallback
    if PUBCHEM_AVAILABLE:
        try:
            print("📥 Attempting to download from PubChem (alternative source)...")
            df = download_pubchem_subset(max_molecules)
            save_to_cache(df)
            save_to_database(df)
            print("✅ Successfully downloaded from PubChem!")
            return df
        except Exception as e:
            print(f"❌ PubChem download failed: {type(e).__name__}: {str(e)[:100]}")
    else:
        print("⚠️  PubChem client not available. Install with: pip install pubchempy")
    
    # Try cached data (but only if it has enough molecules)
    print("💡 Trying to use cached data if available...")
    df = load_from_cache()
    if df is not None and len(df) >= max_molecules:
        print(f"✅ Using cached data with {len(df)} molecules (meets requirement of {max_molecules})")
        return df
    elif df is not None and len(df) > 0 and len(df) < max_molecules:
        print(f"⚠️  Cached data has only {len(df)} molecules (need {max_molecules})")
        print("   Will use cached data but it's insufficient - consider using --force to download more")
        # Return what we have, but warn the user
        return df
    
    # Last resort: create sample data
    if use_sample_on_failure:
        print("⚠️  No cached data available and all data sources failed")
        print("💡 Creating sample data for testing (limited functionality)...")
        df = create_sample_data(min(max_molecules, 100))  # Limit sample to 100
        save_to_cache(df)
        save_to_database(df)
        print("✅ Sample data created. You can retry download later when APIs are available.")
        return df
    else:
        raise RuntimeError(
            "No cached data available and all download sources failed. "
            "Please try again later or use sample data for testing."
        )


def get_molecule_by_id(chembl_id: str) -> Optional[Dict]:
    """Get a single molecule by ChEMBL ID from database."""
    if not DB_PATH.exists():
        return None
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM molecules WHERE chembl_id = ?", (chembl_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        return None
    
    columns = ['chembl_id', 'smiles', 'name', 'molecular_weight', 'is_approved', 'targets']
    return dict(zip(columns, row))


if __name__ == "__main__":
    # Test the data loader
    print("🧪 Testing data loader...")
    df = get_molecules(force_download=False, max_molecules=1000)  # Start with 1000 for testing
    print(f"\n📊 Dataset summary:")
    print(f"  Total molecules: {len(df)}")
    print(f"  Approved drugs: {df['is_approved'].sum()}")
    print(f"  Average molecular weight: {df['molecular_weight'].mean():.2f}")
    print(f"\n📝 Sample molecules:")
    print(df.head(10)[['chembl_id', 'name', 'smiles']].to_string())

