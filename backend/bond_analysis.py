"""
Chemical bond and scaffold analysis using RDKit.
Extracts atom/bond properties, computes Maximum Common Substructure (MCS),
and identifies functional groups.
"""

from typing import Dict, List, Optional, Tuple, Set
from rdkit import Chem
from rdkit.Chem import rdFMCS, rdMolDescriptors, Descriptors
from rdkit.Chem.rdchem import Atom, Bond, Mol


def extract_atom_properties(atom: Atom) -> Dict:
    """
    Extract detailed properties from an RDKit atom.
    
    Args:
        atom: RDKit Atom object
        
    Returns:
        Dictionary with atom properties
    """
    return {
        'symbol': atom.GetSymbol(),
        'atomic_num': atom.GetAtomicNum(),
        'formal_charge': atom.GetFormalCharge(),
        'hybridization': str(atom.GetHybridization()),
        'is_aromatic': atom.GetIsAromatic(),
        'degree': atom.GetDegree(),  # Number of bonds
        'total_valence': atom.GetTotalValence(),
        'num_hydrogens': atom.GetTotalNumHs(),
        'is_in_ring': atom.IsInRing(),
        'chiral_tag': str(atom.GetChiralTag()),
    }


def extract_bond_properties(bond: Bond) -> Dict:
    """
    Extract detailed properties from an RDKit bond.
    
    Args:
        bond: RDKit Bond object
        
    Returns:
        Dictionary with bond properties
    """
    return {
        'atom1': bond.GetBeginAtomIdx(),
        'atom2': bond.GetEndAtomIdx(),
        'order': int(bond.GetBondTypeAsDouble()),
        'is_aromatic': bond.GetIsAromatic(),
        'is_in_ring': bond.IsInRing(),
        'bond_type': str(bond.GetBondType()),
        'stereo': str(bond.GetStereo()),
    }


def extract_atom_bond_data(smiles: str) -> Optional[Dict]:
    """
    Extract complete atom and bond data from a SMILES string.
    
    Args:
        smiles: SMILES string
        
    Returns:
        Dictionary with:
        - atoms: List of atom property dictionaries
        - bonds: List of bond property dictionaries
        - smiles: Original SMILES string
        Or None if SMILES is invalid
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        # Extract atoms
        atoms = []
        for i, atom in enumerate(mol.GetAtoms()):
            atom_data = extract_atom_properties(atom)
            atom_data['index'] = i
            atoms.append(atom_data)
        
        # Extract bonds
        bonds = []
        for bond in mol.GetBonds():
            bond_data = extract_bond_properties(bond)
            bonds.append(bond_data)
        
        return {
            'atoms': atoms,
            'bonds': bonds,
            'smiles': smiles
        }
    
    except Exception as e:
        print(f"Error extracting atom/bond data: {e}")
        return None


def compute_mcs(smiles1: str, smiles2: str, timeout: int = 10) -> Optional[Dict]:
    """
    Compute Maximum Common Substructure (MCS) between two molecules.
    
    Args:
        smiles1: SMILES string of first molecule
        smiles2: SMILES string of second molecule
        timeout: Maximum time in seconds for MCS computation
        
    Returns:
        Dictionary with:
        - mcs_smiles: SMILES of the common substructure
        - num_atoms: Number of atoms in MCS
        - num_bonds: Number of bonds in MCS
        - atom_mapping_1: Mapping from MCS atom indices to molecule 1 atom indices
        - atom_mapping_2: Mapping from MCS atom indices to molecule 2 atom indices
        - bond_mapping_1: Mapping from MCS bond indices to molecule 1 bond indices
        - bond_mapping_2: Mapping from MCS bond indices to molecule 2 bond indices
        - shared_atoms_1: Set of atom indices in molecule 1 that are part of MCS
        - shared_atoms_2: Set of atom indices in molecule 2 that are part of MCS
        - shared_bonds_1: Set of bond indices in molecule 1 that are part of MCS
        - shared_bonds_2: Set of bond indices in molecule 2 that are part of MCS
        Or None if computation fails
    """
    try:
        mol1 = Chem.MolFromSmiles(smiles1)
        mol2 = Chem.MolFromSmiles(smiles2)
        
        if mol1 is None or mol2 is None:
            return None
        
        # Find MCS
        mcs_result = rdFMCS.FindMCS(
            [mol1, mol2],
            timeout=timeout,
            matchValences=True,
            ringMatchesRingOnly=False,
            completeRingsOnly=False
        )
        
        if not mcs_result.numAtoms:
            return None
        
        # Get MCS molecule
        mcs_mol = Chem.MolFromSmarts(mcs_result.smartsString)
        if mcs_mol is None:
            return None
        
        mcs_smiles = Chem.MolToSmiles(mcs_mol)
        
        # Find atom matches using substructure matching
        # Match MCS to molecule 1
        matches1 = mol1.GetSubstructMatches(mcs_mol)
        matches2 = mol2.GetSubstructMatches(mcs_mol)
        
        if not matches1 or not matches2:
            return None
        
        # Use first match (could be improved to find best match)
        match1 = matches1[0]
        match2 = matches2[0]
        
        # Create atom mappings (MCS index -> molecule index)
        atom_mapping_1 = {i: match1[i] for i in range(len(match1))}
        atom_mapping_2 = {i: match2[i] for i in range(len(match2))}
        
        # Find shared atoms (indices in original molecules)
        shared_atoms_1 = set(match1)
        shared_atoms_2 = set(match2)
        
        # Find shared bonds
        # A bond is shared if both its atoms are in the shared set
        shared_bonds_1 = set()
        for bond in mol1.GetBonds():
            bond_idx = bond.GetIdx()
            if bond.GetBeginAtomIdx() in shared_atoms_1 and bond.GetEndAtomIdx() in shared_atoms_1:
                shared_bonds_1.add(bond_idx)
        
        shared_bonds_2 = set()
        for bond in mol2.GetBonds():
            bond_idx = bond.GetIdx()
            if bond.GetBeginAtomIdx() in shared_atoms_2 and bond.GetEndAtomIdx() in shared_atoms_2:
                shared_bonds_2.add(bond_idx)
        
        # Create bond mappings (simplified - map by atom pairs)
        bond_mapping_1 = {}
        bond_mapping_2 = {}
        
        mcs_bonds = mcs_mol.GetBonds()
        for mcs_bond_idx, mcs_bond in enumerate(mcs_bonds):
            mcs_atom1 = mcs_bond.GetBeginAtomIdx()
            mcs_atom2 = mcs_bond.GetEndAtomIdx()
            
            # Find corresponding bond in molecule 1
            mol1_atom1 = atom_mapping_1.get(mcs_atom1)
            mol1_atom2 = atom_mapping_1.get(mcs_atom2)
            if mol1_atom1 is not None and mol1_atom2 is not None:
                bond1 = mol1.GetBondBetweenAtoms(mol1_atom1, mol1_atom2)
                if bond1:
                    bond_mapping_1[mcs_bond_idx] = bond1.GetIdx()
            
            # Find corresponding bond in molecule 2
            mol2_atom1 = atom_mapping_2.get(mcs_atom1)
            mol2_atom2 = atom_mapping_2.get(mcs_atom2)
            if mol2_atom1 is not None and mol2_atom2 is not None:
                bond2 = mol2.GetBondBetweenAtoms(mol2_atom1, mol2_atom2)
                if bond2:
                    bond_mapping_2[mcs_bond_idx] = bond2.GetIdx()
        
        return {
            'mcs_smiles': mcs_smiles,
            'mcs_smarts': mcs_result.smartsString,
            'num_atoms': mcs_result.numAtoms,
            'num_bonds': mcs_result.numBonds,
            'atom_mapping_1': atom_mapping_1,
            'atom_mapping_2': atom_mapping_2,
            'bond_mapping_1': bond_mapping_1,
            'bond_mapping_2': bond_mapping_2,
            'shared_atoms_1': list(shared_atoms_1),
            'shared_atoms_2': list(shared_atoms_2),
            'shared_bonds_1': list(shared_bonds_1),
            'shared_bonds_2': list(shared_bonds_2),
        }
    
    except Exception as e:
        print(f"Error computing MCS: {e}")
        return None


def identify_functional_groups(smiles: str) -> List[Dict]:
    """
    Identify functional groups in a molecule.
    
    Args:
        smiles: SMILES string
        
    Returns:
        List of functional group dictionaries, each with:
        - type: Functional group type (e.g., "hydroxyl", "amine", "aromatic_ring")
        - atoms: List of atom indices involved
        - description: Human-readable description
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return []
        
        functional_groups = []
        
        # Define SMARTS patterns for common functional groups
        patterns = {
            'hydroxyl': '[OH]',
            'carboxyl': 'C(=O)[OH]',
            'amine_primary': '[NH2]',
            'amine_secondary': '[NH]',
            'amine_tertiary': '[N]',
            'amide': 'C(=O)[NH]',
            'ester': 'C(=O)[O]',
            'ether': '[O]',
            'ketone': 'C(=O)',
            'aldehyde': 'C(=O)[H]',
            'aromatic_ring': 'c1ccccc1',  # Benzene ring
            'halogen_fluorine': '[F]',
            'halogen_chlorine': '[Cl]',
            'halogen_bromine': '[Br]',
            'halogen_iodine': '[I]',
            'nitro': '[N+](=O)[O-]',
            'sulfonate': 'S(=O)(=O)[O]',
            'phosphate': 'P(=O)([O])[O]',
        }
        
        # Find matches for each pattern
        for fg_type, smarts in patterns.items():
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is None:
                continue
            
            matches = mol.GetSubstructMatches(pattern)
            for match in matches:
                functional_groups.append({
                    'type': fg_type,
                    'atoms': list(match),
                    'description': _get_functional_group_description(fg_type),
                })
        
        # Identify hydrogen bond donors and acceptors using RDKit
        hbd_atoms = []
        hba_atoms = []
        
        for atom in mol.GetAtoms():
            # Hydrogen bond donors: N or O with attached H
            if atom.GetSymbol() in ['N', 'O']:
                num_h = atom.GetTotalNumHs()
                if num_h > 0:
                    hbd_atoms.append(atom.GetIdx())
            
            # Hydrogen bond acceptors: N, O, F with lone pairs
            if atom.GetSymbol() in ['N', 'O', 'F']:
                # Check if it's not fully saturated
                if atom.GetFormalCharge() == 0:
                    hba_atoms.append(atom.GetIdx())
        
        if hbd_atoms:
            functional_groups.append({
                'type': 'hydrogen_bond_donor',
                'atoms': hbd_atoms,
                'description': 'Hydrogen bond donor atoms (N, O with H)',
            })
        
        if hba_atoms:
            functional_groups.append({
                'type': 'hydrogen_bond_acceptor',
                'atoms': hba_atoms,
                'description': 'Hydrogen bond acceptor atoms (N, O, F)',
            })
        
        # Identify aromatic rings
        ring_info = mol.GetRingInfo()
        aromatic_rings = []
        for ring in ring_info.AtomRings():
            # Check if ring is aromatic
            is_aromatic = all(mol.GetAtomWithIdx(idx).GetIsAromatic() for idx in ring)
            if is_aromatic:
                aromatic_rings.append(list(ring))
        
        if aromatic_rings:
            functional_groups.append({
                'type': 'aromatic_ring_system',
                'atoms': [idx for ring in aromatic_rings for idx in ring],
                'description': f'Aromatic ring system ({len(aromatic_rings)} rings)',
            })
        
        return functional_groups
    
    except Exception as e:
        print(f"Error identifying functional groups: {e}")
        return []


def _get_functional_group_description(fg_type: str) -> str:
    """Get human-readable description for a functional group type."""
    descriptions = {
        'hydroxyl': 'Hydroxyl group (-OH)',
        'carboxyl': 'Carboxyl group (-COOH)',
        'amine_primary': 'Primary amine (-NH2)',
        'amine_secondary': 'Secondary amine (-NH-)',
        'amine_tertiary': 'Tertiary amine (-N<)',
        'amide': 'Amide group (-CONH-)',
        'ester': 'Ester group (-COO-)',
        'ether': 'Ether group (-O-)',
        'ketone': 'Ketone group (C=O)',
        'aldehyde': 'Aldehyde group (-CHO)',
        'aromatic_ring': 'Aromatic ring',
        'halogen_fluorine': 'Fluorine atom',
        'halogen_chlorine': 'Chlorine atom',
        'halogen_bromine': 'Bromine atom',
        'halogen_iodine': 'Iodine atom',
        'nitro': 'Nitro group (-NO2)',
        'sulfonate': 'Sulfonate group',
        'phosphate': 'Phosphate group',
        'hydrogen_bond_donor': 'Hydrogen bond donor',
        'hydrogen_bond_acceptor': 'Hydrogen bond acceptor',
        'aromatic_ring_system': 'Aromatic ring system',
    }
    return descriptions.get(fg_type, fg_type)


def compare_molecules(smiles1: str, smiles2: str) -> Optional[Dict]:
    """
    Compare two molecules and return detailed comparison data.
    
    Args:
        smiles1: SMILES string of first molecule
        smiles2: SMILES string of second molecule
        
    Returns:
        Dictionary with:
        - molecule1: Atom/bond data for molecule 1
        - molecule2: Atom/bond data for molecule 2
        - mcs: MCS comparison data
        - functional_groups_1: Functional groups in molecule 1
        - functional_groups_2: Functional groups in molecule 2
        Or None if comparison fails
    """
    try:
        # Extract atom/bond data
        mol1_data = extract_atom_bond_data(smiles1)
        mol2_data = extract_atom_bond_data(smiles2)
        
        if mol1_data is None or mol2_data is None:
            return None
        
        # Compute MCS
        mcs_data = compute_mcs(smiles1, smiles2)
        
        # Identify functional groups
        fg1 = identify_functional_groups(smiles1)
        fg2 = identify_functional_groups(smiles2)
        
        return {
            'molecule1': mol1_data,
            'molecule2': mol2_data,
            'mcs': mcs_data,
            'functional_groups_1': fg1,
            'functional_groups_2': fg2,
        }
    
    except Exception as e:
        print(f"Error comparing molecules: {e}")
        return None

