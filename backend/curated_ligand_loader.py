"""
Curated ligand loader for cancer mechanism research.
Loads known ligands from curated lists with PubChem CIDs.
This avoids large bulk downloads by using targeted, verified ligand data.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

# Curated ligands for adenosine mechanism targets
# Format: {target_gene_symbol: [list of ligands with PubChem CIDs]}
ADENOSINE_CURATED_LIGANDS = {
    'NT5E': [  # CD73 inhibitors
        {'name': 'APCP', 'pubchem_cid': '1017', 'interaction_type': 'inhibitor'},
        {'name': 'PSB-12379', 'pubchem_cid': '10146145', 'interaction_type': 'inhibitor'},
        {'name': 'AB680', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},  # May need to search
    ],
    'ENTPD1': [  # CD39 inhibitors
        {'name': 'ARL67156', 'pubchem_cid': '5311067', 'interaction_type': 'inhibitor'},
        {'name': 'POM-1', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},  # May need to search
    ],
    'ADORA2A': [  # A2A receptor antagonists
        {'name': 'CGS-15943', 'pubchem_cid': '2690', 'interaction_type': 'antagonist'},
        {'name': 'SCH-58261', 'pubchem_cid': '176408', 'interaction_type': 'antagonist'},
        {'name': 'MSX-2', 'pubchem_cid': '10046145', 'interaction_type': 'antagonist'},
        {'name': 'Preladenant', 'pubchem_cid': None, 'interaction_type': 'antagonist'},  # Search by name
        {'name': 'Istradefylline', 'pubchem_cid': '5311037', 'interaction_type': 'antagonist'},
        {'name': 'CPI-444', 'pubchem_cid': None, 'interaction_type': 'antagonist'},  # Search by name
        {'name': 'AB928', 'pubchem_cid': None, 'interaction_type': 'antagonist'},  # Search by name
    ],
    'ADORA2B': [  # A2B receptor antagonists
        {'name': 'PSB-603', 'pubchem_cid': '10318703', 'interaction_type': 'antagonist'},
        {'name': 'MRS-1754', 'pubchem_cid': None, 'interaction_type': 'antagonist'},  # Search by name
    ],
}

# Curated ligands for PD-1/PD-L1 mechanism targets
PD1_PDL1_CURATED_LIGANDS = {
    'PDCD1': [  # PD-1 inhibitors (mostly antibodies, but some small molecules)
        {'name': 'BMS-202', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},  # Search by name
        {'name': 'BMS-1166', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},  # Search by name
        {'name': 'BMS-1001', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},  # Search by name
        {'name': 'BMS-8', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},  # Search by name
    ],
    'CD274': [  # PD-L1 inhibitors
        {'name': 'BMS-202', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},  # Also targets PD-L1
        {'name': 'BMS-1166', 'pubchem_cid': None, 'interaction_type': 'inhibitor'},
    ],
    'CD279': [  # PD-L2 (less common target)
        # Fewer known ligands for PD-L2
    ],
}


def find_molecule_by_pubchem_cid(pubchem_cid: str, conn: sqlite3.Connection) -> Optional[int]:
    """Find molecule index by PubChem CID."""
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE pubchem_cid = ?", (pubchem_cid,))
    result = cursor.fetchone()
    return result[0] if result else None


def find_molecule_by_smiles(smiles: str, conn: sqlite3.Connection) -> Optional[int]:
    """Find molecule index by SMILES."""
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE smiles = ?", (smiles,))
    result = cursor.fetchone()
    return result[0] if result else None


def load_ligand_from_pubchem_cid(pubchem_cid: str, target_id: int, 
                                 interaction_type: str, ligand_name: str,
                                 conn: sqlite3.Connection) -> Optional[Dict]:
    """
    Load a single ligand from PubChem by CID.
    
    Args:
        pubchem_cid: PubChem Compound ID
        target_id: Target ID in database
        interaction_type: Type of interaction (inhibitor, antagonist, etc.)
        ligand_name: Name of the ligand
        conn: Database connection
        
    Returns:
        Dictionary with ligand data or None
    """
    if not PUBCHEM_AVAILABLE:
        return None
    
    try:
        cursor = conn.cursor()
        
        # Check if ligand already exists
        cursor.execute("""
            SELECT id FROM ligands 
            WHERE pubchem_cid = ? AND target_id = ?
        """, (pubchem_cid, target_id))
        if cursor.fetchone():
            return None  # Already exists
        
        # Fetch compound from PubChem
        time.sleep(0.2)  # Rate limiting
        compound = pcp.Compound.from_cid(int(pubchem_cid))
        
        # Get SMILES (use connectivity_smiles first to avoid deprecation warning)
        smiles = compound.connectivity_smiles or compound.isomeric_smiles or getattr(compound, 'canonical_smiles', None)
        if not smiles:
            return None
        
        # Get name (prefer provided name, fallback to PubChem name)
        name = ligand_name or compound.iupac_name
        if not name and compound.synonyms:
            name = compound.synonyms[0]
        if not name:
            name = f"PubChem_{pubchem_cid}"
        
        # Find molecule in database
        molecule_index = find_molecule_by_pubchem_cid(pubchem_cid, conn)
        if not molecule_index and smiles:
            molecule_index = find_molecule_by_smiles(smiles, conn)
        
        # Insert ligand
        cursor.execute("""
            INSERT INTO ligands (name, smiles, pubchem_cid, interaction_type, target_id, molecule_index)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, smiles, pubchem_cid, interaction_type, target_id, molecule_index))
        
        conn.commit()
        return {
            'id': cursor.lastrowid,
            'name': name,
            'pubchem_cid': pubchem_cid,
            'smiles': smiles
        }
    except Exception as e:
        print(f"   ⚠️  Error loading ligand {ligand_name} (CID {pubchem_cid}): {e}")
        return None


def search_ligand_by_name(ligand_name: str, target_id: int, interaction_type: str,
                          conn: sqlite3.Connection) -> Optional[Dict]:
    """
    Search for a ligand by name in PubChem and load it.
    
    Args:
        ligand_name: Name of the ligand to search for
        target_id: Target ID in database
        interaction_type: Type of interaction
        conn: Database connection
        
    Returns:
        Dictionary with ligand data or None
    """
    if not PUBCHEM_AVAILABLE:
        return None
    
    try:
        cursor = conn.cursor()
        
        # Check if ligand already exists by name
        cursor.execute("""
            SELECT id FROM ligands 
            WHERE name = ? AND target_id = ?
        """, (ligand_name, target_id))
        if cursor.fetchone():
            return None  # Already exists
        
        # Search PubChem by name
        time.sleep(0.2)  # Rate limiting
        compounds = pcp.get_compounds(ligand_name, 'name')
        
        if not compounds:
            return None
        
        # Use first result
        compound = compounds[0]
        cid = str(compound.cid)
        
        # Check if already exists by CID
        cursor.execute("""
            SELECT id FROM ligands 
            WHERE pubchem_cid = ? AND target_id = ?
        """, (cid, target_id))
        if cursor.fetchone():
            return None
        
        # Get SMILES (use connectivity_smiles first to avoid deprecation warning)
        smiles = compound.connectivity_smiles or compound.isomeric_smiles or getattr(compound, 'canonical_smiles', None)
        if not smiles:
            return None
        
        # Find molecule in database
        molecule_index = find_molecule_by_pubchem_cid(cid, conn)
        if not molecule_index and smiles:
            molecule_index = find_molecule_by_smiles(smiles, conn)
        
        # Insert ligand
        cursor.execute("""
            INSERT INTO ligands (name, smiles, pubchem_cid, interaction_type, target_id, molecule_index)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ligand_name, smiles, cid, interaction_type, target_id, molecule_index))
        
        conn.commit()
        return {
            'id': cursor.lastrowid,
            'name': ligand_name,
            'pubchem_cid': cid,
            'smiles': smiles
        }
    except Exception as e:
        print(f"   ⚠️  Error searching for ligand {ligand_name}: {e}")
        return None


def load_curated_ligands_for_target(target_id: int, gene_symbol: str, mechanism_name: str,
                                    conn: sqlite3.Connection) -> int:
    """
    Load curated ligands for a target based on mechanism.
    
    Args:
        target_id: Target ID in database
        gene_symbol: Gene symbol (e.g., 'ADORA2A', 'PDCD1')
        mechanism_name: Mechanism name to determine which curated list to use
        conn: Database connection
        
    Returns:
        Count of successfully loaded ligands
    """
    # Determine which curated list to use
    curated_ligands = None
    if 'Adenosine' in mechanism_name or 'adenosine' in mechanism_name.lower():
        curated_ligands = ADENOSINE_CURATED_LIGANDS.get(gene_symbol, [])
    elif 'PD-1' in mechanism_name or 'PD-L1' in mechanism_name or 'PD1' in mechanism_name.upper():
        curated_ligands = PD1_PDL1_CURATED_LIGANDS.get(gene_symbol, [])
    
    if not curated_ligands:
        return 0
    
    print(f"   📋 Loading {len(curated_ligands)} curated ligands for {gene_symbol}...")
    
    loaded_count = 0
    
    for ligand_data in curated_ligands:
        ligand_name = ligand_data['name']
        pubchem_cid = ligand_data.get('pubchem_cid')
        interaction_type = ligand_data.get('interaction_type', 'inhibitor')
        
        result = None
        
        # Try loading by CID first (faster and more reliable)
        if pubchem_cid:
            result = load_ligand_from_pubchem_cid(
                pubchem_cid, target_id, interaction_type, ligand_name, conn
            )
        
        # If CID loading failed or no CID, try searching by name
        if not result and ligand_name:
            result = search_ligand_by_name(ligand_name, target_id, interaction_type, conn)
        
        if result:
            loaded_count += 1
            print(f"      ✅ Loaded {ligand_name} (CID: {result.get('pubchem_cid', 'N/A')})")
        else:
            print(f"      ⚠️  Could not load {ligand_name}")
    
    return loaded_count


def load_curated_ligands_for_mechanism(mechanism_id: int, conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load curated ligands for all targets in a mechanism.
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        Total count of successfully loaded ligands
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        from target_loader import get_targets_for_mechanism
        
        # Get mechanism name
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM mechanisms WHERE id = ?", (mechanism_id,))
        mechanism_result = cursor.fetchone()
        if not mechanism_result:
            return 0
        mechanism_name = mechanism_result[0]
        
        # Get all targets for this mechanism
        targets = get_targets_for_mechanism(mechanism_id, conn)
        
        if not targets:
            return 0
        
        print(f"📋 Loading curated ligands for mechanism: {mechanism_name}")
        print(f"   Found {len(targets)} targets")
        
        total_loaded = 0
        
        for target in targets:
            target_id = target['id']
            gene_symbol = target.get('gene_symbol')
            
            if not gene_symbol:
                continue
            
            loaded = load_curated_ligands_for_target(
                target_id, gene_symbol, mechanism_name, conn
            )
            total_loaded += loaded
        
        print(f"\n✅ Total curated ligands loaded: {total_loaded}")
        return total_loaded
        
    except Exception as e:
        print(f"❌ Error loading curated ligands: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        if should_close:
            conn.close()
