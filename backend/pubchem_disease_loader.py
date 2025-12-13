"""
PubChem-based disease-drug loader.
Searches PubChem for drugs by disease indication and downloads molecular data.
"""

import time
from pathlib import Path
from typing import List, Dict, Optional, Set
import pandas as pd

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors


def search_drugs_by_disease(disease_name: str, max_drugs: int = 50) -> List[Dict]:
    """
    Search PubChem for drugs used to treat a specific disease.
    
    Args:
        disease_name: Name of the disease (e.g., "Alzheimer's disease")
        max_drugs: Maximum number of drugs to return
        
    Returns:
        List of dictionaries with drug information
    """
    if not PUBCHEM_AVAILABLE:
        raise ImportError("pubchempy is not installed. Install with: pip install pubchempy")
    
    print(f"🔍 Searching PubChem for drugs treating '{disease_name}'...")
    
    drugs = []
    seen_cids = set()
    
    # Search strategies:
    # 1. Search by disease name + "drug" or "treatment"
    # 2. Search for known drugs for the disease
    # 3. Use PubChem's indication search if available
    
    search_terms = [
        f"{disease_name} drug",
        f"{disease_name} treatment",
        disease_name,
    ]
    
    for search_term in search_terms:
        if len(drugs) >= max_drugs:
            break
        
        try:
            # Search PubChem by name/text
            compounds = pcp.get_compounds(search_term, 'name', listkey_count=min(50, max_drugs))
            
            for comp in compounds:
                if len(drugs) >= max_drugs:
                    break
                
                cid = comp.cid
                if not cid or cid in seen_cids:
                    continue
                
                try:
                    # Get SMILES
                    smiles = comp.canonical_smiles or comp.isomeric_smiles or comp.connectivity_smiles
                    if not smiles:
                        continue
                    
                    # Validate SMILES
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        continue
                    
                    # Get molecular weight
                    mw = comp.molecular_weight or rdMolDescriptors.CalcExactMolWt(mol)
                    
                    # Filter for drug-like molecules (MW 100-1000)
                    if mw < 100 or mw > 1000:
                        continue
                    
                    # Get name
                    name = comp.iupac_name
                    if not name and comp.synonyms:
                        # Try to find a drug name in synonyms
                        for synonym in comp.synonyms[:5]:  # Check first 5 synonyms
                            if any(keyword in synonym.lower() for keyword in ['drug', 'medication', 'tablet', 'capsule', 'injection']):
                                continue  # Skip generic terms
                            if len(synonym) < 50:  # Prefer shorter names
                                name = synonym
                                break
                        if not name:
                            name = comp.synonyms[0]
                    
                    if not name:
                        name = f"PubChem_{cid}"
                    
                    drugs.append({
                        'pubchem_cid': str(cid),
                        'name': name,
                        'smiles': smiles,
                        'molecular_weight': mw,
                        'disease': disease_name,
                        'source': 'pubchem_search'
                    })
                    seen_cids.add(cid)
                    
                    if len(drugs) % 10 == 0:
                        print(f"  ✓ Found {len(drugs)} drugs...")
                    
                    # Rate limiting
                    time.sleep(0.2)
                
                except Exception as e:
                    continue
            
            # Delay between search terms
            time.sleep(0.5)
        
        except Exception as e:
            print(f"  ⚠️  Error searching '{search_term}': {e}")
            continue
    
    print(f"✅ Found {len(drugs)} drugs for '{disease_name}'")
    return drugs


def search_known_drugs(drug_names: List[str], disease_name: str) -> List[Dict]:
    """
    Search PubChem for specific known drug names.
    
    Args:
        drug_names: List of drug names to search for
        disease_name: Disease these drugs treat
        
    Returns:
        List of dictionaries with drug information
    """
    if not PUBCHEM_AVAILABLE:
        raise ImportError("pubchempy is not installed. Install with: pip install pubchempy")
    
    print(f"🔍 Searching PubChem for {len(drug_names)} known drugs...")
    
    drugs = []
    seen_cids = set()
    
    for drug_name in drug_names:
        try:
            compounds = pcp.get_compounds(drug_name, 'name')
            
            for comp in compounds:
                cid = comp.cid
                if not cid or cid in seen_cids:
                    continue
                
                try:
                    smiles = comp.canonical_smiles or comp.isomeric_smiles or comp.connectivity_smiles
                    if not smiles:
                        continue
                    
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        continue
                    
                    mw = comp.molecular_weight or rdMolDescriptors.CalcExactMolWt(mol)
                    if mw < 100 or mw > 1000:
                        continue
                    
                    name = comp.iupac_name
                    if not name and comp.synonyms:
                        name = comp.synonyms[0]
                    if not name:
                        name = drug_name
                    
                    drugs.append({
                        'pubchem_cid': str(cid),
                        'name': name,
                        'smiles': smiles,
                        'molecular_weight': mw,
                        'disease': disease_name,
                        'source': 'known_drug'
                    })
                    seen_cids.add(cid)
                    
                    if len(drugs) % 5 == 0:
                        print(f"  ✓ Found {len(drugs)} drugs...")
                    
                    time.sleep(0.2)
                    break  # Take first match for each drug name
                
                except Exception:
                    continue
        
        except Exception as e:
            print(f"  ⚠️  Error searching for '{drug_name}': {e}")
            continue
        
        time.sleep(0.3)
    
    print(f"✅ Found {len(drugs)} drugs from known drug list")
    return drugs


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
    drug_name: Optional[str],
    drug_cid: Optional[str],
    molecule_df: pd.DataFrame
) -> Optional[int]:
    """
    Match a PubChem drug to a molecule in the database.
    
    Args:
        drug_smiles: Drug SMILES from PubChem
        drug_name: Drug name from PubChem
        drug_cid: PubChem CID
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
            # Try exact match
            matches = molecule_df[molecule_df['smiles'].apply(
                lambda x: normalize_smiles(x) == canonical_smiles if x else False
            )]
            if len(matches) > 0:
                return int(matches.index[0])
    
    # Strategy 2: Match by PubChem CID
    if drug_cid and 'pubchem_cid' in molecule_df.columns:
        matches = molecule_df[molecule_df['pubchem_cid'] == drug_cid]
        if len(matches) > 0:
            return int(matches.index[0])
    
    # Strategy 3: Fuzzy name matching
    if drug_name:
        drug_name_lower = drug_name.lower()
        if 'name' in molecule_df.columns:
            # Try exact match
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


def load_disease_drugs_from_pubchem(
    disease_name: str,
    known_drugs: Optional[List[str]] = None,
    max_drugs: int = 50,
    molecule_df: Optional[pd.DataFrame] = None
) -> List[Dict]:
    """
    Load drugs for a disease from PubChem.
    
    Args:
        disease_name: Name of the disease
        known_drugs: Optional list of known drug names to search for
        max_drugs: Maximum number of drugs to find
        molecule_df: Optional DataFrame to match against existing molecules
        
    Returns:
        List of drug-disease relationships
    """
    all_drugs = []
    
    # First, search for known drugs if provided
    if known_drugs:
        known_drug_results = search_known_drugs(known_drugs, disease_name)
        all_drugs.extend(known_drug_results)
    
    # Then, do general search
    if len(all_drugs) < max_drugs:
        remaining = max_drugs - len(all_drugs)
        search_results = search_drugs_by_disease(disease_name, max_drugs=remaining)
        all_drugs.extend(search_results)
    
    # Remove duplicates by PubChem CID
    seen_cids = set()
    unique_drugs = []
    for drug in all_drugs:
        cid = drug.get('pubchem_cid')
        if cid and cid not in seen_cids:
            seen_cids.add(cid)
            unique_drugs.append(drug)
    
    # Match to existing molecules if dataframe provided
    if molecule_df is not None:
        for drug in unique_drugs:
            matched_idx = match_drug_to_molecule(
                drug.get('smiles'),
                drug.get('name'),
                drug.get('pubchem_cid'),
                molecule_df
            )
            drug['matched_molecule_index'] = matched_idx
    
    return unique_drugs


if __name__ == "__main__":
    # Test the loader
    print("🧪 Testing PubChem disease drug loader...")
    
    # Test with Alzheimer's
    alzheimers_drugs = [
        "donepezil", "rivastigmine", "galantamine", "memantine", "tacrine"
    ]
    
    try:
        drugs = load_disease_drugs_from_pubchem(
            disease_name="Alzheimer's disease",
            known_drugs=alzheimers_drugs,
            max_drugs=10
        )
        
        print(f"\n📊 Found {len(drugs)} drugs:")
        for drug in drugs[:5]:
            print(f"  - {drug['name']} (CID: {drug['pubchem_cid']})")
    except Exception as e:
        print(f"❌ Error: {e}")

