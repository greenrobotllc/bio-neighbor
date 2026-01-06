"""
Ligand loader for cancer mechanism research.
Loads ligands from ChEMBL and PubChem, links to molecules table.
"""

import sqlite3
import json
import requests
import time
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False

try:
    from chembl_webresource_client.new_client import new_client
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False
    new_client = None


def find_molecule_by_chembl_id(chembl_id: str, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find molecule index by ChEMBL ID.
    
    Args:
        chembl_id: ChEMBL ID
        conn: Database connection
        
    Returns:
        Molecule index (rowid) or None
    """
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE chembl_id = ?", (chembl_id,))
    result = cursor.fetchone()
    return result[0] if result else None


def find_molecule_by_pubchem_cid(pubchem_cid: str, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find molecule index by PubChem CID.
    
    Args:
        pubchem_cid: PubChem Compound ID
        conn: Database connection
        
    Returns:
        Molecule index (rowid) or None
    """
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE pubchem_cid = ?", (pubchem_cid,))
    result = cursor.fetchone()
    return result[0] if result else None


def find_molecule_by_smiles(smiles: str, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find molecule index by SMILES.
    
    Args:
        smiles: SMILES string
        conn: Database connection
        
    Returns:
        Molecule index (rowid) or None
    """
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE smiles = ?", (smiles,))
    result = cursor.fetchone()
    return result[0] if result else None


def load_ligand_from_chembl(target_id: int, chembl_target_id: str, 
                            interaction_type: str = 'inhibitor',
                            conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load ligands from ChEMBL for a target.
    
    Args:
        target_id: Target ID in database
        chembl_target_id: ChEMBL target ID (e.g., 'CHEMBL1234')
        interaction_type: Type of interaction (agonist/antagonist/inhibitor)
        conn: Optional database connection
        
    Returns:
        Ligand ID if successful, None otherwise
    """
    if not CHEMBL_AVAILABLE:
        print("⚠️  ChEMBL client not available")
        return None
    
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Query ChEMBL for activities on this target
        print(f"📥 Fetching ligands from ChEMBL for target {chembl_target_id}")
        
        try:
            activities = new_client.activity.filter(
                target_chembl_id=chembl_target_id,
                standard_type__in=['IC50', 'Ki', 'Kd', 'EC50'],
                standard_relation='=',
                limit=100  # Limit to top 100 for MVP
            )
        except Exception as e:
            print(f"⚠️  Error querying ChEMBL: {e}")
            return None
        
        ligand_ids = []
        for activity in activities:
            try:
                molecule_chembl_id = activity.get('molecule_chembl_id')
                if not molecule_chembl_id:
                    continue
                
                # Check if ligand already exists
                cursor.execute("""
                    SELECT id FROM ligands 
                    WHERE chembl_id = ? AND target_id = ?
                """, (molecule_chembl_id, target_id))
                existing = cursor.fetchone()
                if existing:
                    ligand_ids.append(existing[0])
                    continue
                
                # Get molecule details from ChEMBL
                try:
                    molecule = new_client.molecule.filter(molecule_chembl_id=molecule_chembl_id).only(['molecule_chembl_id', 'pref_name', 'molecule_structures'])[0]
                except Exception:
                    continue
                
                smiles = None
                if molecule.get('molecule_structures'):
                    smiles = molecule['molecule_structures'].get('canonical_smiles')
                
                name = molecule.get('pref_name') or molecule_chembl_id
                
                # Try to find existing molecule in database
                molecule_index = None
                if molecule_chembl_id:
                    molecule_index = find_molecule_by_chembl_id(molecule_chembl_id, conn)
                
                # Insert ligand
                cursor.execute("""
                    INSERT INTO ligands (name, smiles, chembl_id, interaction_type, target_id, molecule_index)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, smiles, molecule_chembl_id, interaction_type, target_id, molecule_index))
                
                ligand_ids.append(cursor.lastrowid)
                
            except Exception as e:
                print(f"⚠️  Error processing ChEMBL activity: {e}")
                continue
        
        conn.commit()
        print(f"✅ Loaded {len(ligand_ids)} ligands from ChEMBL for target {target_id}")
        return ligand_ids[0] if ligand_ids else None
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading ligands from ChEMBL: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def load_ligand_from_pubchem(target_id: int, pubchem_cid: str,
                             interaction_type: str = 'inhibitor',
                             conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load ligand from PubChem.
    
    Args:
        target_id: Target ID in database
        pubchem_cid: PubChem Compound ID
        interaction_type: Type of interaction
        conn: Optional database connection
        
    Returns:
        Ligand ID if successful, None otherwise
    """
    if not PUBCHEM_AVAILABLE:
        print("⚠️  PubChemPy not available")
        return None
    
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Check if ligand already exists
        cursor.execute("""
            SELECT id FROM ligands 
            WHERE pubchem_cid = ? AND target_id = ?
        """, (pubchem_cid, target_id))
        existing = cursor.fetchone()
        if existing:
            return existing[0]
        
        print(f"📥 Fetching ligand from PubChem: {pubchem_cid}")
        
        try:
            compound = pcp.Compound.from_cid(pubchem_cid)
            name = compound.iupac_name or compound.synonyms[0] if compound.synonyms else f"PubChem_{pubchem_cid}"
            smiles = compound.canonical_smiles
        except Exception as e:
            print(f"⚠️  Error fetching PubChem compound {pubchem_cid}: {e}")
            return None
        
        # Try to find existing molecule in database
        molecule_index = None
        if pubchem_cid:
            molecule_index = find_molecule_by_pubchem_cid(pubchem_cid, conn)
        if not molecule_index and smiles:
            molecule_index = find_molecule_by_smiles(smiles, conn)
        
        # Insert ligand
        cursor.execute("""
            INSERT INTO ligands (name, smiles, pubchem_cid, interaction_type, target_id, molecule_index)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, smiles, pubchem_cid, interaction_type, target_id, molecule_index))
        
        ligand_id = cursor.lastrowid
        conn.commit()
        print(f"✅ Loaded ligand from PubChem (ID: {ligand_id})")
        return ligand_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading ligand from PubChem: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def get_ligands_for_target(target_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all ligands for a target.
    
    Args:
        target_id: Target ID
        conn: Optional database connection
        
    Returns:
        List of ligand dictionaries
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            return []
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM ligands
            WHERE target_id = ?
            ORDER BY name
        """, (target_id,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        ligands = [dict(zip(columns, row)) for row in rows]
        
        return ligands
    finally:
        if should_close:
            conn.close()


def get_ligands_for_mechanism(mechanism_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all ligands for a mechanism (across all targets).
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        List of ligand dictionaries
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            return []
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT l.*
            FROM ligands l
            JOIN targets t ON l.target_id = t.id
            JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ?
            ORDER BY l.name
        """, (mechanism_id,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        ligands = [dict(zip(columns, row)) for row in rows]
        
        return ligands
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # Test loading ligands
    print("🧪 Testing ligand loader...")
    # This would require a target_id and ChEMBL target ID
    # For testing, we'd need to set up a target first
    print("✅ Ligand loader module ready")
