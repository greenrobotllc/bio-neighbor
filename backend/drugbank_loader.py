"""
DrugBank data loader for disease-drug-molecule relationships.
Supports DrugBank API and downloadable XML/CSV files.
"""

import os
import json
import sqlite3
import requests
import xml.etree.ElementTree as ET
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem.inchi import InchiToInchiKey
import pandas as pd

# Import shared configuration from data_loader to ensure consistency
from data_loader import DB_PATH, DATA_DIR

# Configuration
DRUGBANK_CACHE_DIR = DATA_DIR / "drugbank_cache"
DRUGBANK_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# DrugBank API configuration (optional - requires registration)
DRUGBANK_API_BASE = "https://go.drugbank.com/releases/latest"
DRUGBANK_API_KEY = os.environ.get("DRUGBANK_API_KEY", None)

# MeSH ID for Alzheimer's disease
ALZHEIMERS_MESH_ID = "D000544"
ALZHEIMERS_NAMES = [
    "Alzheimer's disease",
    "Alzheimer disease",
    "Alzheimer Disease",
    "Alzheimers Disease",
    "AD",
    "Alzheimer",
]


def normalize_smiles(smiles: str) -> Optional[str]:
    """
    Normalize SMILES string to canonical form for matching.
    
    Args:
        smiles: SMILES string
        
    Returns:
        Canonical SMILES or None if invalid
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return None


def match_drug_to_molecule(
    drug_smiles: Optional[str],
    drug_inchi: Optional[str],
    drug_name: Optional[str],
    molecule_df: pd.DataFrame
) -> Optional[int]:
    """
    Match a DrugBank drug to a molecule in the database.
    
    Args:
        drug_smiles: Drug SMILES from DrugBank
        drug_inchi: Drug InChI from DrugBank
        drug_name: Drug name from DrugBank
        molecule_df: DataFrame with existing molecules
        
    Returns:
        Index of matched molecule in database, or None if no match
    """
    if molecule_df is None or len(molecule_df) == 0:
        return None
    
    # Strategy 1: Match by canonical SMILES
    if drug_smiles:
        canonical_smiles = normalize_smiles(drug_smiles)
        if canonical_smiles:
            # Use precomputed canonical_smiles column if available, otherwise compute on-the-fly
            if 'canonical_smiles' in molecule_df.columns:
                matches = molecule_df[molecule_df['canonical_smiles'] == canonical_smiles]
            else:
                # Fallback: compute on-the-fly (slower)
                matches = molecule_df[molecule_df['smiles'].apply(
                    lambda x: normalize_smiles(x) == canonical_smiles if x else False
                )]
            if len(matches) > 0:
                return int(matches.index[0])
    
    # Strategy 2: Match by InChI/InChIKey
    if drug_inchi:
        # Try InChI match
        if 'inchi' in molecule_df.columns:
            matches = molecule_df[molecule_df['inchi'].str.contains(
                drug_inchi[:20], na=False, regex=False
            )]
            if len(matches) > 0:
                return int(matches.index[0])
        
        # Try InChIKey match (first 14 chars are standard)
        if 'inchikey' in molecule_df.columns:
            # Convert InChI to InChIKey for proper matching
            # InChI and InChIKey are different formats - cannot slice InChI to get InChIKey
            try:
                drug_inchikey = InchiToInchiKey(drug_inchi)
                if drug_inchikey:
                    # Normalize case (InChIKey is case-insensitive but stored may vary)
                    drug_inchikey = drug_inchikey.upper()
                    # Use first 14 chars (standard block) for matching
                    inchikey_prefix = drug_inchikey[:14] if len(drug_inchikey) >= 14 else drug_inchikey
                    # Match against normalized inchikey column
                    matches = molecule_df[molecule_df['inchikey'].str.upper().str.startswith(
                        inchikey_prefix, na=False
                    )]
                    if len(matches) > 0:
                        return int(matches.index[0])
            except Exception:
                # If RDKit conversion fails, skip InChIKey matching
                pass
    
    # Strategy 3: Fuzzy name matching (case-insensitive partial match)
    if drug_name:
        drug_name_lower = drug_name.lower()
        # Try exact name match first
        if 'name' in molecule_df.columns:
            matches = molecule_df[molecule_df['name'].str.lower() == drug_name_lower]
            if len(matches) > 0:
                return int(matches.index[0])
            
            # Try partial match
            matches = molecule_df[molecule_df['name'].str.lower().str.contains(
                drug_name_lower, na=False, regex=False
            )]
            if len(matches) > 0:
                return int(matches.index[0])
    
    return None


def parse_drugbank_xml(xml_path: Path, target_disease: Optional[str] = None) -> List[Dict]:
    """
    Parse DrugBank XML file and extract disease-drug relationships.
    
    Args:
        xml_path: Path to DrugBank XML file
        target_disease: Optional disease name to filter (e.g., "Alzheimer's disease")
        
    Returns:
        List of dictionaries with drug-disease relationships
    """
    print(f"📖 Parsing DrugBank XML: {xml_path.name}")
    
    relationships = []
    
    try:
        # Use iterparse for large XML files (memory efficient)
        # Note: If XML can be user-supplied or from untrusted sources, consider using
        # defusedxml.ElementTree.iterparse() instead to prevent XML bomb attacks
        context = ET.iterparse(xml_path, events=('start', 'end'))
        context = iter(context)
        event, root = next(context)
        
        drug_count = 0
        for event, elem in context:
            if event == 'end' and elem.tag == '{http://www.drugbank.ca}drug':
                drug_count += 1
                
                try:
                    # Extract drug information
                    drug_id = None
                    drug_name = None
                    drug_smiles = None
                    drug_inchi = None
                    indications = []
                    
                    # Get drug ID
                    drugbank_id_elem = elem.find('{http://www.drugbank.ca}drugbank-id')
                    if drugbank_id_elem is not None:
                        drug_id = drugbank_id_elem.text
                    
                    # Get drug name
                    name_elem = elem.find('{http://www.drugbank.ca}name')
                    if name_elem is not None:
                        drug_name = name_elem.text
                    
                    # Get SMILES
                    properties = elem.find('{http://www.drugbank.ca}calculated-properties')
                    if properties is not None:
                        for prop in properties.findall('{http://www.drugbank.ca}property'):
                            kind = prop.find('{http://www.drugbank.ca}kind')
                            value = prop.find('{http://www.drugbank.ca}value')
                            if kind is not None and value is not None:
                                if kind.text == 'SMILES':
                                    drug_smiles = value.text
                                elif kind.text == 'InChI':
                                    drug_inchi = value.text
                    
                    # Get indications (diseases)
                    indications_elem = elem.find('{http://www.drugbank.ca}indications')
                    if indications_elem is not None:
                        for indication in indications_elem.findall('{http://www.drugbank.ca}indication'):
                            indication_text = indication.text
                            if indication_text:
                                indications.append(indication_text.strip())
                    
                    # Filter by target disease if specified (and only keep matching indications)
                    if target_disease:
                        td = target_disease.lower()
                        # Filter indications to only those matching target_disease
                        matching_indications = [i for i in indications if td in i.lower()]
                        if not matching_indications:
                            elem.clear()
                            continue
                        # Use only matching indications for relationships
                        indications = matching_indications
                    
                    # Store relationship
                    if drug_id and (drug_smiles or drug_name) and indications:
                        for indication in indications:
                            relationships.append({
                                'drugbank_id': drug_id,
                                'drug_name': drug_name,
                                'smiles': drug_smiles,
                                'inchi': drug_inchi,
                                'disease': indication,
                                'indication_type': 'approved'  # Default, could be enhanced
                            })
                    
                    if drug_count % 100 == 0:
                        print(f"  ✓ Processed {drug_count} drugs, found {len(relationships)} relationships...")
                
                except Exception as e:
                    # Skip drugs that fail to parse
                    pass
                
                # Clear element to free memory
                elem.clear()
                root.clear()
        
        print(f"✅ Parsed {drug_count} drugs, found {len(relationships)} disease-drug relationships")
        return relationships
    
    except Exception as e:
        print(f"❌ Error parsing DrugBank XML: {e}")
        return []


def download_drugbank_sample() -> Optional[Path]:
    """
    Download a sample DrugBank dataset (if available via API).
    For full implementation, users should download DrugBank XML manually.
    
    Returns:
        Path to downloaded file, or None if download fails
    """
    print("📥 Attempting to download DrugBank data...")
    print("   Note: Full DrugBank data requires registration at https://go.drugbank.com")
    print("   For now, we'll use a sample approach or manual file.")
    
    # Check if user has provided a DrugBank file
    sample_file = DRUGBANK_CACHE_DIR / "drugbank.xml"
    if sample_file.exists():
        print(f"✅ Found existing DrugBank file: {sample_file}")
        return sample_file
    
    # Try to download a sample (this would require API key)
    if DRUGBANK_API_KEY:
        try:
            # This is a placeholder - actual API endpoint would be different
            print("   Using DrugBank API (requires valid API key)...")
            # API call would go here
            return None
        except Exception as e:
            print(f"   API download failed: {e}")
    
    print("⚠️  No DrugBank data found. Please download DrugBank XML file manually.")
    print(f"   Place it at: {sample_file}")
    print("   Or set DRUGBANK_API_KEY environment variable for API access.")
    return None


def load_alzheimers_drugs_from_sample() -> List[Dict]:
    """
    Load Alzheimer's disease drugs from a curated sample list.
    This is a fallback when DrugBank XML is not available.
    
    Returns:
        List of drug-disease relationships
    """
    print("📝 Loading Alzheimer's disease drugs from curated sample...")
    
    # Curated list of Alzheimer's drugs with SMILES
    # Source: Common Alzheimer's medications
    alzheimers_drugs = [
        {
            'drugbank_id': 'DB00682',
            'drug_name': 'Donepezil',
            'smiles': 'CC(=O)OCCN1CCCC1c2ccc(C(=O)O)cc2',
            'disease': "Alzheimer's disease",
            'indication_type': 'approved'
        },
        {
            'drugbank_id': 'DB00314',
            'drug_name': 'Rivastigmine',
            'smiles': 'CC(=O)OCc1ccc(C(=O)OC)cc1N(C)C',
            'disease': "Alzheimer's disease",
            'indication_type': 'approved'
        },
        {
            'drugbank_id': 'DB00343',
            'drug_name': 'Galantamine',
            'smiles': 'COc1cc2c(cc1OC)CC(C3CC(=O)Nc4ccccc34)N2',
            'disease': "Alzheimer's disease",
            'indication_type': 'approved'
        },
        {
            'drugbank_id': 'DB01042',
            'drug_name': 'Memantine',
            'smiles': 'CC(C)(C)NC1CCC2(CC1)CCCCC2',
            'disease': "Alzheimer's disease",
            'indication_type': 'approved'
        },
        {
            'drugbank_id': 'DB01264',
            'drug_name': 'Tacrine',
            'smiles': 'Cc1cc2c(cc1N)CCc3ccccc3N2',
            'disease': "Alzheimer's disease",
            'indication_type': 'approved'
        },
    ]
    
    print(f"✅ Loaded {len(alzheimers_drugs)} Alzheimer's disease drugs from sample")
    return alzheimers_drugs


def load_drugs_from_pubchem(
    disease_name: str,
    known_drugs: Optional[List[str]] = None,
    max_drugs: int = 50
) -> List[Dict]:
    """
    Load drugs for a disease from PubChem.
    
    Args:
        disease_name: Name of the disease
        known_drugs: Optional list of known drug names
        max_drugs: Maximum number of drugs to find
        
    Returns:
        List of drug-disease relationships
    """
    try:
        from .pubchem_disease_loader import load_disease_drugs_from_pubchem
    except ImportError:
        try:
            # Try absolute import if relative fails
            from pubchem_disease_loader import load_disease_drugs_from_pubchem
        except ImportError:
            print("⚠️  PubChem disease loader not available")
            return []
    
    try:
        relationships = load_disease_drugs_from_pubchem(
            disease_name=disease_name,
            known_drugs=known_drugs,
            max_drugs=max_drugs
        )
        
        # Convert to drugbank_loader format
        result = []
        for drug in relationships:
            result.append({
                'drugbank_id': f"PUBCHEM_{drug.get('pubchem_cid', 'UNKNOWN')}",
                'drug_name': drug.get('name', ''),
                'smiles': drug.get('smiles'),
                'inchi': None,  # PubChem loader doesn't provide InChI yet
                'disease': disease_name,
                'indication_type': 'approved',
                'matched_molecule_index': drug.get('matched_molecule_index')
            })
        
        return result
    except Exception as e:
        print(f"⚠️  Error loading from PubChem: {e}")
        return []


def load_drugbank_data(
    target_disease: Optional[str] = "Alzheimer's disease",
    use_sample: bool = True,
    use_pubchem: bool = True
) -> List[Dict]:
    """
    Load DrugBank data for a specific disease.
    
    Args:
        target_disease: Disease name to filter (default: "Alzheimer's disease")
        use_sample: If True, use sample data if DrugBank XML not available
        
    Returns:
        List of drug-disease relationships
    """
    # Try to find DrugBank XML file
    xml_file = DRUGBANK_CACHE_DIR / "drugbank.xml"
    
    if xml_file.exists():
        print(f"📂 Found DrugBank XML file: {xml_file}")
        relationships = parse_drugbank_xml(xml_file, target_disease=target_disease)
        if relationships:
            return relationships
    
    # Try to download
    downloaded_file = download_drugbank_sample()
    if downloaded_file and downloaded_file.exists():
        relationships = parse_drugbank_xml(downloaded_file, target_disease=target_disease)
        if relationships:
            return relationships
    
    # Try PubChem if enabled
    if use_pubchem:
        if not target_disease:
            print("⚠️  target_disease is required when use_pubchem=True")
            return []
        
        print("📥 Attempting to load from PubChem...")
        try:
            from .top_100_diseases import get_disease_by_name, get_alzheimers_drugs
        except ImportError:
            try:
                # Try absolute import if relative fails
                from top_100_diseases import get_disease_by_name, get_alzheimers_drugs
            except ImportError:
                print("⚠️  top_100_diseases module not available")
                return []
        
        try:
            # Get known drugs for this disease
            disease_info = get_disease_by_name(target_disease)
            known_drugs = None
            if disease_info:
                known_drugs = disease_info[2]  # Get drug list
            elif "alzheimer" in target_disease.lower():
                known_drugs = get_alzheimers_drugs()
            
            pubchem_relationships = load_drugs_from_pubchem(
                disease_name=target_disease,
                known_drugs=known_drugs,
                max_drugs=50
            )
            
            if pubchem_relationships:
                print(f"✅ Loaded {len(pubchem_relationships)} drugs from PubChem")
                return pubchem_relationships
        except Exception as e:
            print(f"⚠️  PubChem loading failed: {e}")
    
    # Fallback to sample data
    if use_sample and target_disease and "alzheimer" in target_disease.lower():
        return load_alzheimers_drugs_from_sample()
    
    print("⚠️  No DrugBank data available")
    return []


def load_top_100_diseases_drugs(
    max_diseases: int = 100,
    max_drugs_per_disease: int = 20,
    molecule_df: Optional[pd.DataFrame] = None
) -> List[Dict]:
    """
    Load drugs for top 100 diseases from PubChem.
    
    Args:
        max_diseases: Maximum number of diseases to process
        max_drugs_per_disease: Maximum drugs per disease
        molecule_df: Optional DataFrame to match against
        
    Returns:
        List of all drug-disease relationships
    """
    try:
        from .top_100_diseases import get_top_100_diseases
    except ImportError:
        # Try absolute import if relative fails
        try:
            from top_100_diseases import get_top_100_diseases
        except ImportError:
            print("⚠️  Top 100 diseases module not available")
            return []
    
    all_relationships = []
    diseases = get_top_100_diseases()[:max_diseases]
    
    print(f"📥 Loading drugs for {len(diseases)} diseases from PubChem...")
    print("   This may take a while due to rate limiting...")
    
    for i, (disease_name, mesh_id, known_drugs) in enumerate(diseases, 1):
        print(f"\n[{i}/{len(diseases)}] Processing: {disease_name}")
        
        try:
            relationships = load_drugs_from_pubchem(
                disease_name=disease_name,
                known_drugs=known_drugs,
                max_drugs=max_drugs_per_disease
            )
            
            # Match to molecules if dataframe provided
            if molecule_df is not None:
                for rel in relationships:
                    matched_idx = match_drug_to_molecule(
                        rel.get('smiles'),
                        rel.get('inchi'),
                        rel.get('drug_name'),
                        molecule_df
                    )
                    rel['matched_molecule_index'] = matched_idx
            
            all_relationships.extend(relationships)
            
            # Rate limiting between diseases
            time.sleep(1)
        
        except Exception as e:
            print(f"  ⚠️  Error processing {disease_name}: {e}")
            continue
    
    print(f"\n✅ Loaded {len(all_relationships)} total drug-disease relationships")
    return all_relationships


def save_drugs_to_db(
    drugs: List[Dict],
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, int]:
    """
    Save drugs to the drugs table.
    
    Args:
        drugs: List of drug information dictionaries
        conn: Optional database connection (creates new if None)
        
    Returns:
        Dictionary with statistics: {'drugs_added': int}
    """
    if not DB_PATH.exists():
        return {'drugs_added': 0}
    
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Initialize drugs table schema
        try:
            from .drug_schema import create_drugs_table
        except ImportError:
            try:
                from drug_schema import create_drugs_table
            except ImportError:
                from backend.drug_schema import create_drugs_table
        create_drugs_table(conn)
        
        drugs_added = 0
        
        for drug in drugs:
            # Normalize name field (handle both 'name' and 'drug_name' keys)
            name = drug.get('name') or drug.get('drug_name')
            if not name:
                # Skip drugs without a name (required NOT NULL field)
                continue
            
            # Check if drug already exists (by pubchem_cid or name)
            existing_id = None
            if drug.get('pubchem_cid'):
                cursor.execute("SELECT id FROM drugs WHERE pubchem_cid = ?", (drug['pubchem_cid'],))
                result = cursor.fetchone()
                if result:
                    existing_id = result[0]
            
            if existing_id is None and name:
                cursor.execute("SELECT id FROM drugs WHERE name = ? AND generic_name = ?", 
                             (name, drug.get('generic_name')))
                result = cursor.fetchone()
                if result:
                    existing_id = result[0]
            
            if existing_id:
                # Update existing drug
                cursor.execute("""
                    UPDATE drugs SET
                        brand_names = ?,
                        description = ?,
                        indication = ?,
                        active_ingredients = ?,
                        inactive_ingredients = ?,
                        dosage_form = ?,
                        route = ?
                    WHERE id = ?
                """, (
                    json.dumps(drug.get('brand_names', [])),
                    drug.get('description'),
                    drug.get('indication'),
                    json.dumps(drug.get('active_ingredients', [])),
                    json.dumps(drug.get('inactive_ingredients', [])),
                    drug.get('dosage_form'),
                    drug.get('route'),
                    existing_id
                ))
            else:
                # Insert new drug
                cursor.execute("""
                    INSERT INTO drugs (
                        name, generic_name, brand_names, pubchem_cid, drugbank_id,
                        description, indication, active_ingredients, inactive_ingredients,
                        dosage_form, route
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    drug.get('generic_name'),
                    json.dumps(drug.get('brand_names', [])),
                    drug.get('pubchem_cid'),
                    drug.get('drugbank_id'),
                    drug.get('description'),
                    drug.get('indication'),
                    json.dumps(drug.get('active_ingredients', [])),
                    json.dumps(drug.get('inactive_ingredients', [])),
                    drug.get('dosage_form'),
                    drug.get('route')
                ))
                drugs_added += 1
        
        conn.commit()
        return {'drugs_added': drugs_added}
    
    finally:
        if should_close:
            conn.close()


def save_disease_data_to_db(
    relationships: List[Dict],
    molecule_df: pd.DataFrame,
    drugs: Optional[List[Dict]] = None
) -> Dict[str, int]:
    """
    Save disease-drug relationships to database.
    
    Args:
        relationships: List of drug-disease relationships from DrugBank
        molecule_df: DataFrame with existing molecules
        
    Returns:
        Dictionary with statistics: {'diseases_added': int, 'relationships_added': int, 'matched_drugs': int}
    """
    if not DB_PATH.exists():
        print("⚠️  Molecules database not found. Please run data setup first.")
        return {'diseases_added': 0, 'relationships_added': 0, 'matched_drugs': 0, 'drugs_added': 0}
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure database schema is up to date
    try:
        from .db_migrations import migrate_database
    except ImportError:
        try:
            from db_migrations import migrate_database
        except ImportError:
            from backend.db_migrations import migrate_database
    migrate_database(conn)
    
    # Save drugs if provided
    drugs_added = 0
    drug_id_map = {}  # Map drug names/CIDs to drug IDs
    
    if drugs:
        drugs_stats = save_drugs_to_db(drugs, conn)
        drugs_added = drugs_stats['drugs_added']
        
        # Build map of drug names/CIDs to drug IDs
        for drug in drugs:
            cursor.execute("SELECT id FROM drugs WHERE pubchem_cid = ? OR name = ?", 
                         (drug.get('pubchem_cid'), drug.get('name')))
            result = cursor.fetchone()
            if result:
                key = drug.get('pubchem_cid') or drug.get('name')
                if key:
                    drug_id_map[key] = result[0]
    
    # Tables are created by migration system - no need to create them here
    
    # Track statistics
    diseases_added = 0
    relationships_added = 0
    matched_drugs = 0
    disease_cache = {}  # Cache disease IDs by name
    
    # Process relationships
    for rel in relationships:
        disease_name = rel.get('disease', '').strip()
        if not disease_name:
            continue
        
        # Get or create disease
        if disease_name not in disease_cache:
            cursor.execute("SELECT id FROM diseases WHERE name = ?", (disease_name,))
            result = cursor.fetchone()
            if result:
                disease_id = result[0]
            else:
                # Determine MeSH ID if known
                mesh_id = None
                if "alzheimer" in disease_name.lower():
                    mesh_id = ALZHEIMERS_MESH_ID
                
                cursor.execute(
                    "INSERT INTO diseases (name, mesh_id) VALUES (?, ?)",
                    (disease_name, mesh_id)
                )
                disease_id = cursor.lastrowid
                diseases_added += 1
            
            disease_cache[disease_name] = disease_id
        
        disease_id = disease_cache[disease_name]
        
        # Match drug to molecule
        molecule_index = match_drug_to_molecule(
            rel.get('smiles'),
            rel.get('inchi'),
            rel.get('drug_name'),
            molecule_df
        )
        
        # Try to find associated drug_id
        drug_id = None
        drug_key = rel.get('pubchem_cid') or rel.get('drug_name')
        if drug_key and drug_key in drug_id_map:
            drug_id = drug_id_map[drug_key]
        
        if molecule_index is not None:
            # Check if relationship already exists
            cursor.execute(
                "SELECT id FROM drug_diseases WHERE molecule_index = ? AND disease_id = ?",
                (molecule_index, disease_id)
            )
            if cursor.fetchone() is None:
                # Insert with drug_id if available
                if drug_id:
                    cursor.execute(
                        "INSERT INTO drug_diseases (molecule_index, disease_id, drug_id, indication_type) VALUES (?, ?, ?, ?)",
                        (molecule_index, disease_id, drug_id, rel.get('indication_type', 'approved'))
                    )
                else:
                    cursor.execute(
                        "INSERT INTO drug_diseases (molecule_index, disease_id, indication_type) VALUES (?, ?, ?)",
                        (molecule_index, disease_id, rel.get('indication_type', 'approved'))
                    )
                relationships_added += 1
                matched_drugs += 1
        elif drug_id:
            # If we have a drug_id but no molecule match, still create relationship
            cursor.execute(
                "SELECT id FROM drug_diseases WHERE drug_id = ? AND disease_id = ?",
                (drug_id, disease_id)
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO drug_diseases (drug_id, disease_id, indication_type) VALUES (?, ?, ?)",
                    (drug_id, disease_id, rel.get('indication_type', 'approved'))
                )
                relationships_added += 1
        else:
            # Drug not matched - could log for future reference
            pass
    
    conn.commit()
    conn.close()
    
    stats = {
        'diseases_added': diseases_added,
        'relationships_added': relationships_added,
        'matched_drugs': matched_drugs,
        'drugs_added': drugs_added
    }
    
    print(f"✅ Saved to database: {diseases_added} diseases, {relationships_added} relationships, {matched_drugs} matched drugs, {drugs_added} drugs")
    return stats


if __name__ == "__main__":
    # Test the loader
    print("🧪 Testing DrugBank loader...")
    
    # Load molecule database
    from data_loader import load_from_database
    molecule_df = load_from_database()
    
    if molecule_df is None or len(molecule_df) == 0:
        print("⚠️  No molecules in database. Please run data setup first.")
    else:
        # Precompute canonical SMILES for all molecules to avoid redundant RDKit calls
        # This is O(n) instead of O(n*m) where n=molecules, m=drugs
        if 'canonical_smiles' not in molecule_df.columns and 'smiles' in molecule_df.columns:
            print("   Precomputing canonical SMILES for molecule matching...")
            from rdkit import Chem
            molecule_df = molecule_df.copy()
            molecule_df['canonical_smiles'] = molecule_df['smiles'].apply(
                lambda x: normalize_smiles(x) if x else None
            )
            print(f"   ✅ Precomputed canonical SMILES for {len(molecule_df)} molecules")
        print(f"📊 Loaded {len(molecule_df)} molecules from database")
        
        # Load Alzheimer's disease drugs
        relationships = load_drugbank_data(target_disease="Alzheimer's disease")
        
        if relationships:
            print(f"\n📋 Found {len(relationships)} drug-disease relationships")
            for rel in relationships[:5]:  # Show first 5
                print(f"  - {rel['drug_name']} -> {rel['disease']}")
            
            # Save to database
            stats = save_disease_data_to_db(relationships, molecule_df)
            print(f"\n📊 Statistics: {stats}")

