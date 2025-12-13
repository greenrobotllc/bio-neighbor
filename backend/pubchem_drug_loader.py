"""
PubChem-based drug information loader.
Fetches complete drug information including brand names, active ingredients, etc.
"""

import time
import json
from typing import List, Dict, Optional
import pandas as pd

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors


def fetch_drug_info_from_pubchem(
    drug_name: str,
    pubchem_cid: Optional[str] = None
) -> Optional[Dict]:
    """
    Fetch complete drug information from PubChem.
    
    Args:
        drug_name: Name of the drug (generic or brand)
        pubchem_cid: Optional PubChem CID if known
        
    Returns:
        Dictionary with drug information or None if not found
    """
    if not PUBCHEM_AVAILABLE:
        return None
    
    try:
        # Search for compound
        if pubchem_cid:
            try:
                comp = pcp.Compound.from_cid(int(pubchem_cid))
            except (ValueError, TypeError, Exception) as e:
                comp = None
        else:
            compounds = pcp.get_compounds(drug_name, 'name')
            if not compounds:
                return None
            comp = compounds[0]
        
        if comp is None:
            return None
        
        # Get basic information
        cid = comp.cid
        smiles = comp.connectivity_smiles or comp.isomeric_smiles or (comp.canonical_smiles if hasattr(comp, 'canonical_smiles') else None)
        
        # Get synonyms (brand names, generic names, etc.)
        synonyms = comp.synonyms or []
        
        # Try to identify generic name and brand names
        generic_name = None
        brand_names = []
        
        # Generic names are often the IUPAC name or first synonym
        if comp.iupac_name:
            generic_name = comp.iupac_name
        
        # Look for brand names in synonyms (often shorter, trademarked names)
        for synonym in synonyms[:20]:  # Check first 20 synonyms
            # Skip very long names (likely IUPAC)
            if len(synonym) > 50:
                continue
            # Skip if it's clearly a chemical name
            if any(char in synonym for char in ['(', ')', '[', ']', '1-', '2-', '3-']):
                continue
            # Brand names are often shorter and don't contain numbers
            if len(synonym) < 30 and not any(char.isdigit() for char in synonym):
                if generic_name is None:
                    generic_name = synonym
                else:
                    brand_names.append(synonym)
        
        # If we still don't have a generic name, use the first reasonable synonym
        if generic_name is None and synonyms:
            generic_name = synonyms[0]
        
        # Get description/summary - use comp.title directly (Title is not a valid get_properties parameter)
        description = None
        try:
            if hasattr(comp, 'title') and comp.title:
                description = comp.title
        except Exception as e:
            print(f"  ⚠️  Could not get description for {drug_name}: {e}")
        
        # Get indication/use from PubChem (if available)
        indication = None
        # Note: Indication is not available via get_properties - would need separate API call
        
        # Extract active ingredients
        # For now, the compound itself is the active ingredient
        # In a full implementation, we'd look for related compounds or substances
        active_ingredients = []
        if smiles:
            active_ingredients.append({
                'smiles': smiles,
                'name': generic_name or drug_name,
                'pubchem_cid': str(cid)
            })
        
        # Inactive ingredients are not typically in PubChem compound data
        # They would need to come from DrugBank or FDA data
        inactive_ingredients = []
        
        drug_info = {
            'name': generic_name or drug_name,
            'generic_name': generic_name,
            'brand_names': brand_names[:10],  # Limit to 10 brand names
            'pubchem_cid': str(cid),
            'drugbank_id': None,  # Would need DrugBank integration
            'description': description or f"Drug information for {generic_name or drug_name}",
            'indication': indication,
            'active_ingredients': active_ingredients,
            'inactive_ingredients': inactive_ingredients,
            'dosage_form': None,  # Would need additional data source
            'route': None,  # Would need additional data source
            'smiles': smiles,
            'molecular_weight': comp.molecular_weight or 0
        }
        
        return drug_info
    
    except Exception as e:
        print(f"  ⚠️  Error fetching drug info for '{drug_name}': {e}")
        return None


def match_active_ingredients_to_molecules(
    active_ingredients: List[Dict],
    molecule_df: pd.DataFrame
) -> List[int]:
    """
    Match active ingredient SMILES to molecules in database.
    
    Args:
        active_ingredients: List of active ingredient dicts with 'smiles'
        molecule_df: DataFrame with existing molecules
        
    Returns:
        List of molecule indices that match active ingredients
    """
    if molecule_df is None or len(molecule_df) == 0:
        return []
    
    matched_indices = []
    
    # Pre-compute canonical SMILES for the DataFrame (do this once outside the loop)
    if 'canonical_smiles' not in molecule_df.columns:
        molecule_df = molecule_df.copy()
        molecule_df['canonical_smiles'] = molecule_df['smiles'].apply(
            lambda x: Chem.MolToSmiles(Chem.MolFromSmiles(x), canonical=True) 
            if x and Chem.MolFromSmiles(x) else None
        )
    
    for ingredient in active_ingredients:
        smiles = ingredient.get('smiles')
        if not smiles:
            continue
        
        # Normalize SMILES
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            canonical_smiles = Chem.MolToSmiles(mol, canonical=True)
        except:
            continue
        
        # Match by pre-computed canonical SMILES
        matches = molecule_df[molecule_df['canonical_smiles'] == canonical_smiles]
        
        if len(matches) > 0:
            matched_indices.append(int(matches.index[0]))
    
    return matched_indices


def load_drug_info(
    drug_name: str,
    pubchem_cid: Optional[str] = None,
    molecule_df: Optional[pd.DataFrame] = None
) -> Optional[Dict]:
    """
    Load complete drug information from PubChem and match to molecules.
    
    Args:
        drug_name: Name of the drug
        pubchem_cid: Optional PubChem CID
        molecule_df: Optional DataFrame to match active ingredients
        
    Returns:
        Dictionary with complete drug information including matched molecule indices
    """
    drug_info = fetch_drug_info_from_pubchem(drug_name, pubchem_cid)
    
    if drug_info is None:
        return None
    
    # Match active ingredients to molecules
    if molecule_df is not None:
        matched_indices = match_active_ingredients_to_molecules(
            drug_info.get('active_ingredients', []),
            molecule_df
        )
        drug_info['active_ingredient_molecule_indices'] = matched_indices
    else:
        drug_info['active_ingredient_molecule_indices'] = []
    
    return drug_info


def load_drugs_for_disease(
    disease_name: str,
    known_drug_names: List[str],
    molecule_df: Optional[pd.DataFrame] = None
) -> List[Dict]:
    """
    Load drug information for multiple drugs used to treat a disease.
    
    Args:
        disease_name: Name of the disease
        known_drug_names: List of known drug names
        molecule_df: Optional DataFrame to match active ingredients
        
    Returns:
        List of drug information dictionaries
    """
    if not PUBCHEM_AVAILABLE:
        return []
    
    print(f"📥 Loading drug information for {len(known_drug_names)} drugs...")
    
    drugs = []
    
    for drug_name in known_drug_names:
        try:
            drug_info = load_drug_info(drug_name, molecule_df=molecule_df)
            
            if drug_info:
                # Add disease association
                drug_info['disease'] = disease_name
                drugs.append(drug_info)
                print(f"  ✓ Loaded: {drug_info.get('name', drug_name)}")
            
            # Rate limiting
            time.sleep(0.3)
        
        except Exception as e:
            print(f"  ⚠️  Error loading '{drug_name}': {e}")
            continue
    
    print(f"✅ Loaded {len(drugs)} drugs")
    return drugs


if __name__ == "__main__":
    # Test the loader
    print("🧪 Testing PubChem drug loader...")
    
    test_drugs = ["donepezil", "rivastigmine", "galantamine"]
    
    try:
        from data_loader import load_from_database
        molecule_df = load_from_database()
        
        for drug_name in test_drugs:
            print(f"\n🔍 Loading: {drug_name}")
            drug_info = load_drug_info(drug_name, molecule_df=molecule_df)
            if drug_info:
                print(f"  Name: {drug_info.get('name')}")
                print(f"  Generic: {drug_info.get('generic_name')}")
                print(f"  Brand names: {drug_info.get('brand_names', [])[:3]}")
                print(f"  Active ingredients matched: {len(drug_info.get('active_ingredient_molecule_indices', []))}")
    except Exception as e:
        print(f"❌ Error: {e}")

