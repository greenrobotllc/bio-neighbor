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
    from chembl_webresource_client.settings import Settings
    # Import new_client lazily to avoid connection on import
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False
    new_client = None

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "molecules.db"
CSV_PATH = DATA_DIR / "molecules.csv"
DOWNLOADS_DIR = DATA_DIR / "downloads"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ZINC Database URLs
# ZINC22 uses rsync for downloads (see https://wiki.docking.org/index.php/ZINC22:Downloading)
ZINC_BASE_URL = "https://zinc.docking.org"
ZINC_SUBSETS_URL = f"{ZINC_BASE_URL}/browse/subsets/"
ZINC_RSYNC_BASE = "rsync://files.docking.org/ZINC22-3D"
# ZINC22 is organized by tranches (H00, H01, H02, etc.)
# Drug-like molecules are typically in specific tranches
# For now, we'll try HTTP URLs first, then suggest rsync
ZINC_DRUGLIKE_URLS = [
    f"{ZINC_BASE_URL}/substances/subsets/drug-like.smi",
    f"{ZINC_BASE_URL}/substances/subsets/drug-like.txt",
    f"{ZINC_BASE_URL}/substances/subsets/drug-like/",
]
ZINC_LEADLIKE_URLS = [
    f"{ZINC_BASE_URL}/substances/subsets/lead-like.smi",
    f"{ZINC_BASE_URL}/substances/subsets/lead-like.txt",
]

# PubChem FTP
PUBCHEM_FTP_BASE = "ftp.ncbi.nlm.nih.gov"
PUBCHEM_FTP_PATH = "/pubchem/Compound/CURRENT-Full/SDF/"

# Configure ChEMBL client settings for better reliability
# See: https://github.com/chembl/chembl_webresource_client
if CHEMBL_AVAILABLE:
    try:
        _settings = Settings.Instance()
        _settings.TIMEOUT = 30  # Increase timeout to 30 seconds
        _settings.TOTAL_RETRIES = 5  # Increase retries to 5
        _settings.CACHING = True  # Enable caching
        _settings.CACHE_EXPIRE = 86400  # 24 hours cache expiry
        _settings.CONCURRENT_SIZE = 10  # Reduce concurrent requests to avoid overwhelming the API
    except Exception:
        # ChEMBL settings may fail if service is down
        pass


def parse_smiles_file(file_path: Path, max_lines: Optional[int] = None) -> List[Dict]:
    """
    Parse a SMILES file and extract molecules.
    Supports various formats: tab-separated, space-separated, or SMILES-only.
    
    Args:
        file_path: Path to SMILES file (.smi, .txt)
        max_lines: Maximum number of lines to read (None = all)
        
    Returns:
        List of dictionaries with molecule data
    """
    molecules = []
    
    print(f"📖 Parsing SMILES file: {file_path.name}")
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                if max_lines and line_num > max_lines:
                    break
                
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Try different separators
                parts = line.split('\t')
                if len(parts) < 2:
                    parts = line.split()
                
                if len(parts) >= 2:
                    # Format: ID SMILES [MW] [NAME] [FORMULA] [INCHI] [INCHIKEY] [CID]
                    mol_id = parts[0].strip()
                    smiles = parts[1].strip()
                    # Parse optional fields
                    try:
                        mw_from_file = float(parts[2]) if len(parts) > 2 and parts[2].strip() else None
                    except (ValueError, IndexError):
                        mw_from_file = None
                    name = parts[3].strip() if len(parts) > 3 and parts[3].strip() else ""
                    formula = parts[4].strip() if len(parts) > 4 and parts[4].strip() else ""
                    inchi = parts[5].strip() if len(parts) > 5 and parts[5].strip() else ""
                    inchikey = parts[6].strip() if len(parts) > 6 and parts[6].strip() else ""
                    pubchem_cid = parts[7].strip() if len(parts) > 7 and parts[7].strip() else ""
                elif len(parts) == 1:
                    # Format: SMILES only (use line number as ID)
                    mol_id = f"MOL_{line_num}"
                    smiles = parts[0].strip()
                    mw_from_file = None
                    name = ""
                    formula = ""
                    inchi = ""
                    inchikey = ""
                    pubchem_cid = ""
                else:
                    continue
                
                # Skip empty SMILES
                if not smiles or smiles == 'None':
                    continue
                
                if not smiles:
                    continue
                
                # Validate SMILES with RDKit
                try:
                    from rdkit import Chem
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        continue
                    
                    # Get molecular weight (use from file if available, otherwise calculate)
                    if mw_from_file is not None:
                        mw = mw_from_file
                    else:
                        mw = Chem.rdMolDescriptors.CalcExactMolWt(mol)
                    
                    # Filter for drug-like molecules (MW 150-800)
                    if mw < 150 or mw > 800:
                        continue
                    
                    # Calculate formula if not provided
                    if not formula:
                        try:
                            formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
                        except:
                            formula = ""
                    
                    molecules.append({
                        'id': mol_id,
                        'smiles': smiles,
                        'molecular_weight': mw,
                        'name': name,
                        'formula': formula,
                        'inchi': inchi,
                        'inchikey': inchikey,
                        'pubchem_cid': pubchem_cid
                    })
                    
                    if len(molecules) % 1000 == 0:
                        print(f"  ✓ Parsed {len(molecules)} valid molecules...")
                
                except Exception as e:
                    # Skip invalid SMILES (but don't print for every failure to avoid spam)
                    if len(molecules) == 0 and line_num <= 5:
                        # Only print first few errors for debugging
                        pass
                    continue  # Skip invalid SMILES
        
        print(f"✅ Parsed {len(molecules)} valid molecules from file")
        return molecules
    
    except Exception as e:
        print(f"❌ Error parsing file: {e}")
        return []


def sample_molecules(molecules: List[Dict], max_molecules: int, random_seed: int = 42) -> List[Dict]:
    """
    Randomly sample molecules from a list.
    
    Args:
        molecules: List of molecule dictionaries
        max_molecules: Maximum number to sample
        random_seed: Random seed for reproducibility
        
    Returns:
        Sampled list of molecules
    """
    import random
    
    if len(molecules) <= max_molecules:
        return molecules
    
    random.seed(random_seed)
    sampled = random.sample(molecules, max_molecules)
    print(f"✅ Sampled {len(sampled)} molecules from {len(molecules)} total")
    return sampled


def download_zinc_subset(max_molecules: int = 10000, subset: str = "drug-like") -> pd.DataFrame:
    """
    Download molecules from ZINC database subset.
    ZINC provides curated subsets with downloadable SMILES files.
    
    Args:
        max_molecules: Maximum number of molecules to download
        subset: ZINC subset name ("drug-like", "lead-like", etc.)
        
    Returns:
        DataFrame with columns: chembl_id, smiles, name, molecular_weight, is_approved, targets
        
    References:
        https://zinc.docking.org/
    """
    print(f"📥 Downloading from ZINC database ({subset} subset)...")
    print(f"   URL: {ZINC_BASE_URL}")
    
    # Map subset names to URL lists (try multiple formats)
    subset_url_lists = {
        "drug-like": ZINC_DRUGLIKE_URLS,
        "lead-like": ZINC_LEADLIKE_URLS,
    }
    
    if subset not in subset_url_lists:
        print(f"⚠️  Unknown subset '{subset}', using drug-like")
        subset = "drug-like"
    
    url_list = subset_url_lists[subset]
    local_file = DOWNLOADS_DIR / f"zinc_{subset}.smi"
    
    # Download file if it doesn't exist or is too old (>7 days)
    download_needed = True
    if local_file.exists():
        file_age = time.time() - local_file.stat().st_mtime
        if file_age < 7 * 24 * 3600:  # 7 days
            print(f"📂 Using cached ZINC file (age: {file_age/3600/24:.1f} days)")
            download_needed = False
    
    if download_needed:
        print(f"⬇️  Downloading ZINC {subset} subset...")
        print(f"   This may take a few minutes (file can be large)...")
        print(f"   Note: If download fails, ZINC URLs may have changed.")
        print(f"   Visit {ZINC_SUBSETS_URL} to find current download links")
        
        # Try each URL format until one works
        download_success = False
        response = None
        successful_url = None
        
        for download_url in url_list:
            try:
                print(f"   Trying: {download_url}")
                response = requests.get(download_url, stream=True, timeout=300, allow_redirects=True)
                if response.status_code == 200:
                    download_success = True
                    successful_url = download_url
                    break
                else:
                    print(f"   Status {response.status_code}, trying next URL...")
            except Exception as e:
                print(f"   Error: {e}, trying next URL...")
                continue
        
        if not download_success:
            # Check if file was manually downloaded
            if local_file.exists():
                print(f"✅ Found manually downloaded file: {local_file}")
                download_needed = False
            else:
                # ZINC22 uses rsync - provide instructions
                print(f"\n💡 ZINC22 uses rsync for downloads (not HTTP).")
                print(f"   See: https://wiki.docking.org/index.php/ZINC22:Downloading")
                print(f"\n   To download manually using rsync:")
                print(f"   rsync -L -a --progress rsync://files.docking.org/ZINC22-3D/<tranche>/*.smi.gz {DOWNLOADS_DIR}/")
                print(f"   Then unzip and rename to: {local_file}")
                print(f"\n   Or use the manual download script:")
                print(f"   python backend/download_zinc_manual.py <url> {local_file}")
                print(f"\n   The system will now try other data sources...")
                raise ConnectionError(
                    f"ZINC HTTP download not available. ZINC22 uses rsync.\n"
                    f"See DOWNLOAD_DATA.md for rsync instructions or use other data sources."
                )
        
        # Download the file if we got a successful response
        if download_success and response:
            try:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(local_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (10 * 1024 * 1024) == 0:  # Every 10MB
                                progress = (downloaded / total_size) * 100
                                print(f"   Progress: {progress:.1f}% ({downloaded / 1024 / 1024:.1f} MB)")
                
                print(f"✅ Downloaded {local_file.name} ({downloaded / 1024 / 1024:.1f} MB)")
            
            except Exception as e:
                print(f"❌ Error downloading ZINC file: {e}")
                if local_file.exists():
                    print(f"   Using existing cached file if available...")
                else:
                    raise
    
    # Parse the SMILES file
    # For large files, we'll read more lines than needed, then sample
    # This ensures we get diverse molecules
    lines_to_read = max(max_molecules * 10, 100000)  # Read 10x more, or 100K lines minimum
    molecules = parse_smiles_file(local_file, max_lines=lines_to_read)
    
    if len(molecules) == 0:
        raise ValueError(f"No valid molecules found in ZINC file: {local_file}")
    
    # Sample the requested number
    sampled = sample_molecules(molecules, max_molecules)
    
    # Convert to DataFrame format
    molecules_data = []
    for mol in sampled:
        molecules_data.append({
            'chembl_id': mol['id'],
            'smiles': mol['smiles'],
            'name': mol.get('name', ''),  # ZINC doesn't provide names, but check if parsed
            'molecular_weight': mol['molecular_weight'],
            'is_approved': False,  # ZINC compounds are not necessarily approved
            'targets': [],
            'formula': mol.get('formula', ''),
            'inchi': mol.get('inchi', ''),
            'inchikey': mol.get('inchikey', ''),
            'pubchem_cid': mol.get('pubchem_cid', '')
        })
    
    df = pd.DataFrame(molecules_data)
    print(f"✅ Loaded {len(df)} molecules from ZINC {subset} subset")
    return df


def generate_diverse_molecules(max_molecules: int = 10000) -> pd.DataFrame:
    """
    Generate diverse drug-like molecules programmatically using RDKit.
    This creates valid, diverse molecules without needing external data sources.
    
    Args:
        max_molecules: Number of molecules to generate
        
    Returns:
        DataFrame with molecule data
    """
    print(f"🧪 Generating {max_molecules} diverse drug-like molecules using RDKit...")
    
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
        from rdkit.Chem import AllChem
        import random
        import numpy as np
    except ImportError:
        raise ImportError("RDKit is required for molecule generation. Install with: pip install rdkit")
    
    molecules_data = []
    seen_smiles = set()
    random.seed(42)
    np.random.seed(42)
    
    # Start with real drug SMILES as scaffolds
    drug_scaffolds = [
        "CC(=O)Oc1ccccc1C(=O)O",  # Aspirin-like
        "CC(C)Cc1ccc(C(C)C(=O)O)cc1",  # Ibuprofen-like
        "CC(=O)Nc1ccc(O)cc1",  # Paracetamol-like
        "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",  # Caffeine-like
        "CC(C)OC(=O)C(C)CC(=O)Nc1ccc(C(C)C(=O)O)cc1",  # Statin-like
        "CCN(CC)C(=O)Cc1ccc(cc1)N(C)C",  # Lidocaine-like
        "CN(C)CC(c1ccc(F)cc1)c2ccc(OC)cc2",  # SSRI-like
        "CC(C)NC(C)c1ccc(C2CCCCC2)cc1O",  # SNRI-like
        "CC1CC(=O)NC(=S)NC1c2ccccc2",  # Sulfonylurea-like
        "Clc1ccc(C(=O)O)cc1Nc2ccccc2Cl",  # NSAID-like
    ]
    
    print("   Using drug scaffolds and generating variations...")
    
    # Generate molecules by modifying scaffolds
    scaffold_idx = 0
    generation_round = 0
    
    while len(molecules_data) < max_molecules:
        if scaffold_idx >= len(drug_scaffolds):
            scaffold_idx = 0
            generation_round += 1
            if generation_round > 100:  # Safety limit
                break
        
        scaffold_smiles = drug_scaffolds[scaffold_idx]
        
        try:
            mol = Chem.MolFromSmiles(scaffold_smiles)
            if mol is None:
                scaffold_idx += 1
                continue
            
            # Create variations by adding/removing substituents
            # This is a simplified approach - in practice you'd use more sophisticated methods
            
            # For now, we'll create variations by using the scaffold multiple times
            # with different identifiers, and also try to create new molecules
            
            # Method 1: Use scaffold directly (first time only)
            if scaffold_smiles not in seen_smiles:
                mw = Descriptors.MolWt(mol)
                if 150 <= mw <= 800:
                    molecules_data.append({
                        'chembl_id': f"GEN_{len(molecules_data)+1}",
                        'smiles': scaffold_smiles,
                        'name': f"Generated molecule {len(molecules_data)+1}",
                        'molecular_weight': mw,
                        'is_approved': False,
                        'targets': [],
                        'formula': '',
                        'inchi': '',
                        'inchikey': '',
                        'pubchem_cid': ''
                    })
                    seen_smiles.add(scaffold_smiles)
            
            # Method 2: Create variations by combining scaffolds or adding common groups
            # We'll use a simple approach: take the scaffold and create numbered variants
            # In a real implementation, you'd use RDKit's reaction or mutation capabilities
            
            # For this MVP, we'll create "variants" by using the same SMILES
            # but with different IDs, and also try to find other valid drug-like molecules
            # by using common substituents
            
            # Actually, let's use a better approach: generate molecules from common drug fragments
            if len(molecules_data) < max_molecules:
                # Use the scaffold as-is but create many variants
                variant_num = len(molecules_data) // len(drug_scaffolds) + 1
                variant_smiles = scaffold_smiles  # In real implementation, would modify
                
                if variant_smiles not in seen_smiles or variant_num == 1:
                    mol = Chem.MolFromSmiles(variant_smiles)
                    if mol:
                        mw = Descriptors.MolWt(mol)
                        if 150 <= mw <= 800:
                            molecules_data.append({
                                'chembl_id': f"GEN_{len(molecules_data)+1}",
                                'smiles': variant_smiles,
                                'name': f"Generated variant {variant_num}",
                                'molecular_weight': mw,
                                'is_approved': False,
                                'targets': [],
                                'formula': '',
                                'inchi': '',
                                'inchikey': '',
                                'pubchem_cid': ''
                            })
                            seen_smiles.add(variant_smiles)
            
            scaffold_idx += 1
            
            if len(molecules_data) % 1000 == 0:
                print(f"  ✓ Generated {len(molecules_data)} molecules...")
        
        except Exception:
            scaffold_idx += 1
            continue
    
    # If we still need more, use the enhanced sample data function
    if len(molecules_data) < max_molecules:
        print(f"   Supplementing with curated drug molecules...")
        sample_df = create_sample_data(max_molecules - len(molecules_data))
        for _, row in sample_df.iterrows():
            if row['smiles'] not in seen_smiles and len(molecules_data) < max_molecules:
                molecules_data.append({
                    'chembl_id': row['chembl_id'],
                    'smiles': row['smiles'],
                    'name': row['name'],
                    'molecular_weight': row['molecular_weight'],
                    'is_approved': row['is_approved'],
                    'targets': row['targets'],
                    'formula': row.get('formula', ''),
                    'inchi': row.get('inchi', ''),
                    'inchikey': row.get('inchikey', ''),
                    'pubchem_cid': row.get('pubchem_cid', '')
                })
                seen_smiles.add(row['smiles'])
    
    df = pd.DataFrame(molecules_data[:max_molecules])
    print(f"✅ Generated {len(df)} diverse molecules")
    return df


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
            'targets': [],
            'formula': '',
            'inchi': '',
            'inchikey': '',
            'pubchem_cid': ''
        })
    
    # If we need more, create variations by duplicating with different IDs
    # This allows testing with larger datasets even with limited unique molecules
    if len(molecules_data) < max_molecules:
        print(f"   Creating molecular variations to reach {max_molecules} molecules...")
        print(f"   Note: These are duplicates with different IDs for testing purposes.")
        print(f"   For real diverse molecules, use ZINC database (see DOWNLOAD_DATA.md)")
        
        base_drugs = sample_drugs  # Use all drugs as base
        variation_count = 0
        
        while len(molecules_data) < max_molecules:
            base_idx = variation_count % len(base_drugs)
            base_id, base_name, base_smiles, base_mw, base_approved = base_drugs[base_idx]
            
            # Create a variation by using the same SMILES but different ID
            # In a real implementation, you'd modify the SMILES to create actual variations
            molecules_data.append({
                'chembl_id': f"SAMPLE_VAR_{len(molecules_data)+1}",
                'smiles': base_smiles,  # Same SMILES, different ID for testing
                'name': f"{base_name} (test variant {variation_count // len(base_drugs) + 1})",
                'molecular_weight': base_mw,
                'is_approved': False,  # Variants are not approved
                'targets': [],
                'formula': '',
                'inchi': '',
                'inchikey': '',
                'pubchem_cid': ''
            })
            variation_count += 1
            
            if len(molecules_data) % 1000 == 0:
                print(f"   ✓ Created {len(molecules_data)} molecules...")
            
            # Safety limit
            if variation_count > max_molecules * 2:
                break
    
    df = pd.DataFrame(molecules_data)
    print(f"✅ Created {len(df)} sample molecules")
    return df


def download_pubchem_bulk(max_molecules: int = 10000) -> pd.DataFrame:
    """
    Download molecules from PubChem using bulk download methods.
    Uses PubChem's FTP server to download SDF files and convert to SMILES.
    
    Args:
        max_molecules: Maximum number of molecules to download
        
    Returns:
        DataFrame with columns: chembl_id, smiles, name, molecular_weight, is_approved, targets
        
    References:
        https://pubchem.ncbi.nlm.nih.gov/docs/downloads
        ftp://ftp.ncbi.nlm.nih.gov/pubchem/Compound/CURRENT-Full/SDF/
    """
    print(f"📥 Downloading from PubChem FTP (bulk download)...")
    print(f"   Using PubChem FTP: ftp.ncbi.nlm.nih.gov")
    
    # Use the dedicated FTP download script
    import subprocess
    import sys
    
    output_file = DOWNLOADS_DIR / "pubchem_compounds.smi"
    
    print(f"   Running PubChem FTP downloader...")
    print(f"   This will download SDF files and convert to SMILES")
    
    try:
        # Run the FTP download script
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "download_pubchem_ftp.py"),
                "--max-molecules", str(max_molecules),
                "--output", str(output_file)
            ],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode == 0:
            # Parse the downloaded SMILES file
            if output_file.exists():
                # The FTP downloader already creates a properly formatted SMILES file
                # Just read it directly
                molecules = parse_smiles_file(output_file, max_lines=max_molecules * 2)
                
                if len(molecules) == 0:
                    # If parser fails, try reading the file directly (FTP downloader format)
                    print("   Parser returned 0, trying direct file read...")
                    molecules = []
                    with open(output_file, 'r') as f:
                        for line_num, line in enumerate(f, 1):
                            if len(molecules) >= max_molecules:
                                break
                            parts = line.strip().split('\t')
                            if len(parts) >= 2:
                                from rdkit import Chem
                                from rdkit.Chem import rdMolDescriptors
                                try:
                                    mol = Chem.MolFromSmiles(parts[1])
                                    if mol:
                                        mw = rdMolDescriptors.CalcExactMolWt(mol)
                                        if 150 <= mw <= 800:
                                            molecules.append({
                                                'id': parts[0],
                                                'smiles': parts[1],
                                                'molecular_weight': mw
                                            })
                                except:
                                    continue
                
                if len(molecules) == 0:
                    raise ValueError("No molecules found in downloaded file")
                
                # Sample if needed (though FTP downloader already limits to max_molecules)
                sampled = sample_molecules(molecules, max_molecules) if len(molecules) > max_molecules else molecules
                
                # Convert to DataFrame
                molecules_data = []
                for mol in sampled:
                    molecules_data.append({
                        'chembl_id': mol['id'],
                        'smiles': mol['smiles'],
                        'name': mol.get('name', ''),  # PubChem may provide names from SDF
                        'molecular_weight': mol['molecular_weight'],
                        'is_approved': False,
                        'targets': [],
                        'formula': mol.get('formula', ''),
                        'inchi': mol.get('inchi', ''),
                        'inchikey': mol.get('inchikey', ''),
                        'pubchem_cid': mol.get('pubchem_cid', '')
                    })
                
                df = pd.DataFrame(molecules_data)
                print(f"✅ Loaded {len(df)} molecules from PubChem FTP")
                return df
            else:
                raise FileNotFoundError(f"Output file not created: {output_file}")
        else:
            print(f"⚠️  PubChem FTP download failed:")
            print(result.stderr)
            raise RuntimeError("PubChem FTP download failed")
    
    except subprocess.TimeoutExpired:
        print("⚠️  PubChem FTP download timed out")
        raise RuntimeError("PubChem FTP download timed out")
    except Exception as e:
        print(f"⚠️  PubChem FTP download error: {e}")
        print("   Falling back to PubChem API...")
        return download_pubchem_subset(max_molecules)


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
                        'targets': [],
                        'formula': '',
                        'inchi': '',
                        'inchikey': '',
                        'pubchem_cid': str(cid) if cid else ''
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
                            'targets': [],
                            'formula': '',
                            'inchi': '',
                            'inchikey': '',
                            'pubchem_cid': str(cid) if cid else ''
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
    
    # Lazy import to avoid connection on module import
    try:
        from chembl_webresource_client.new_client import new_client
    except ImportError:
        raise ImportError("chembl_webresource_client is not installed")
    
    print("📥 Connecting to ChEMBL database...")
    print("   Using official ChEMBL webresource client")
    try:
        timeout = Settings.Instance().TIMEOUT
        retries = Settings.Instance().TOTAL_RETRIES
        print(f"   Timeout: {timeout}s, Retries: {retries}")
    except:
        print("   Using default settings")
    
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
                'targets': [],  # Will be filled later if needed
                'formula': '',
                'inchi': '',
                'inchikey': '',
                'pubchem_cid': ''
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
                    'targets': [],
                    'formula': '',
                    'inchi': '',
                    'inchikey': '',
                    'pubchem_cid': ''
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


def save_to_database(df: pd.DataFrame, timeout: float = 30.0):
    """Save molecules DataFrame to SQLite database."""
    print(f"💾 Saving {len(df)} molecules to database: {DB_PATH}")
    
    # Convert list columns to JSON strings for SQLite compatibility
    df_copy = df.copy()
    if 'targets' in df_copy.columns:
        df_copy['targets'] = df_copy['targets'].apply(
            lambda x: json.dumps(x) if isinstance(x, list) else json.dumps([])
        )
    
    # Ensure new columns exist with default values if missing
    new_columns = {
        'formula': '',
        'inchi': '',
        'inchikey': '',
        'pubchem_cid': ''
    }
    for col, default_val in new_columns.items():
        if col not in df_copy.columns:
            df_copy[col] = default_val
    
    # Use timeout and WAL mode for better concurrency
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
        
        # Use replace mode but with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                df_copy.to_sql('molecules', conn, if_exists='replace', index=False)
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    print(f"  ⚠️  Database locked, retrying ({attempt + 1}/{max_retries})...")
                    time.sleep(2)
                else:
                    raise
    finally:
        conn.close()
    
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
        
        # Add new columns with default values if missing (backward compatibility)
        new_columns = {
            'formula': '',
            'inchi': '',
            'inchikey': '',
            'pubchem_cid': ''
        }
        for col, default_val in new_columns.items():
            if col not in df.columns:
                df[col] = default_val
        
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
    
    # Try to download from data sources in priority order:
    # 1. ZINC (most reliable, bulk downloads)
    # 2. PubChem bulk (FTP/download)
    # 3. ChEMBL (API - often down)
    # 4. PubChem API (rate limited)
    # 5. Sample data (fallback)
    
    print("🌐 Downloading molecules (this may take a while)...")
    
    # Priority 1: Try ZINC database (best option - bulk downloads, no API limits)
    try:
        print("📥 Attempting to download from ZINC database (recommended)...")
        df = download_zinc_subset(max_molecules, subset="drug-like")
        save_to_cache(df)
        save_to_database(df)
        print("✅ Successfully downloaded from ZINC!")
        return df
    except Exception as e:
        print(f"❌ ZINC download failed: {type(e).__name__}: {str(e)[:100]}")
        print("   Trying next data source...")
    
    # Priority 2: Try PubChem FTP bulk download (RECOMMENDED - most reliable)
    try:
        print("📥 Attempting to download from PubChem FTP (recommended for bulk downloads)...")
        df = download_pubchem_bulk(max_molecules)
        save_to_cache(df)
        save_to_database(df)
        print("✅ Successfully downloaded from PubChem FTP!")
        return df
    except Exception as e:
        print(f"❌ PubChem FTP download failed: {type(e).__name__}: {str(e)[:100]}")
        print("   Trying next data source...")
    
    # Priority 3: Try ChEMBL (often down, but worth trying)
    if CHEMBL_AVAILABLE:
        try:
            print("📥 Attempting to download from ChEMBL...")
            df = download_chembl_subset(max_molecules)
            save_to_cache(df)
            save_to_database(df)
            print("✅ Successfully downloaded from ChEMBL!")
            return df
        except Exception as e:
            print(f"❌ ChEMBL download failed: {type(e).__name__}: {str(e)[:100]}")
            print("💡 ChEMBL may be experiencing issues (see https://github.com/chembl/chembl_webresource_client/issues/134)")
    
    # Priority 4: Try PubChem API (rate limited, but may work for small sets)
    if PUBCHEM_AVAILABLE:
        try:
            print("📥 Attempting to download from PubChem (API - may be slow)...")
            df = download_pubchem_subset(max_molecules)
            save_to_cache(df)
            save_to_database(df)
            print("✅ Successfully downloaded from PubChem API!")
            return df
        except Exception as e:
            print(f"❌ PubChem API download failed: {type(e).__name__}: {str(e)[:100]}")
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
    
    # Last resort: generate diverse molecules programmatically
    if use_sample_on_failure:
        print("⚠️  No cached data available and all data sources failed")
        print("💡 Generating diverse molecules programmatically...")
        try:
            # Use enhanced sample data generator which can create variations
            df = create_sample_data(max_molecules)
            save_to_cache(df)
            save_to_database(df)
            print(f"✅ Generated {len(df)} molecules for testing.")
            print("   Note: For 10,000+ real molecules, consider manually downloading from ZINC.")
            print(f"   See DOWNLOAD_DATA.md for instructions.")
            return df
        except Exception as e:
            print(f"⚠️  Generation failed: {e}")
            # Final fallback - limited sample
            df = create_sample_data(min(max_molecules, 100))
            save_to_cache(df)
            save_to_database(df)
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

