"""
Target loader for cancer mechanism research.
Fetches target protein data from UniProt and IUPHAR Guide to Pharmacology.
"""

import sqlite3
import json
import requests
import time
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

# UniProt REST API base URL
UNIPROT_API_BASE = "https://rest.uniprot.org"

# IUPHAR Guide to Pharmacology API
IUPHAR_API_BASE = "https://www.guidetopharmacology.org/services"


def fetch_uniprot_target(uniprot_id: str) -> Optional[Dict]:
    """
    Fetch target information from UniProt API.
    
    Args:
        uniprot_id: UniProt accession ID (e.g., 'P21589')
        
    Returns:
        Dictionary with target information or None
    """
    try:
        url = f"{UNIPROT_API_BASE}/uniprotkb/{uniprot_id}.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract relevant information
        target_info = {
            'uniprot_id': uniprot_id,
            'gene_symbol': None,
            'protein_name': None,
            'function': None,
            'cellular_location': None,
        }
        
        # Extract gene symbol
        if 'genes' in data and data['genes']:
            gene = data['genes'][0]
            if 'geneName' in gene:
                target_info['gene_symbol'] = gene['geneName'].get('value')
        
        # Extract protein name
        if 'proteinDescription' in data:
            desc = data['proteinDescription']
            if 'recommendedName' in desc:
                target_info['protein_name'] = desc['recommendedName'].get('fullName', {}).get('value')
        
        # Extract function
        if 'comments' in data:
            for comment in data['comments']:
                if comment.get('commentType') == 'FUNCTION':
                    if 'texts' in comment:
                        target_info['function'] = ' '.join([t.get('value', '') for t in comment['texts']])
        
        # Extract cellular location
        if 'comments' in data:
            for comment in data['comments']:
                if comment.get('commentType') == 'SUBCELLULAR LOCATION':
                    if 'subcellularLocations' in comment:
                        locations = []
                        for loc in comment['subcellularLocations']:
                            if 'location' in loc:
                                locations.append(loc['location'].get('value', ''))
                        target_info['cellular_location'] = ', '.join(locations)
        
        return target_info
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error fetching UniProt data for {uniprot_id}: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Error parsing UniProt data for {uniprot_id}: {e}")
        return None


def fetch_iuphar_target(uniprot_id: str) -> Optional[Dict]:
    """
    Fetch target pharmacology data from IUPHAR Guide to Pharmacology.
    
    Args:
        uniprot_id: UniProt accession ID
        
    Returns:
        Dictionary with IUPHAR data or None
    """
    try:
        # IUPHAR API endpoint for targets by UniProt ID
        url = f"{IUPHAR_API_BASE}/targets.json"
        params = {'uniprot': uniprot_id}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data or len(data) == 0:
            return None
        
        # Get first matching target
        target_data = data[0]
        
        iuphar_info = {
            'ligand_types': [],
        }
        
        # Extract ligand types if available
        if 'ligands' in target_data:
            ligand_types = set()
            for ligand in target_data['ligands']:
                if 'type' in ligand:
                    ligand_types.add(ligand['type'].lower())
            iuphar_info['ligand_types'] = list(ligand_types)
        
        return iuphar_info
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error fetching IUPHAR data for {uniprot_id}: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Error parsing IUPHAR data for {uniprot_id}: {e}")
        return None


def load_target_from_uniprot(uniprot_id: str, cancer_role: Optional[str] = None, 
                             ligand_types: Optional[List[str]] = None,
                             conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load target from UniProt API into database.
    
    Args:
        uniprot_id: UniProt accession ID
        cancer_role: Optional description of role in cancer
        ligand_types: Optional list of ligand interaction types
        conn: Optional database connection
        
    Returns:
        Target ID if successful, None otherwise
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Check if target already exists
        cursor.execute("SELECT id FROM targets WHERE uniprot_id = ?", (uniprot_id,))
        existing = cursor.fetchone()
        if existing:
            print(f"✅ Target {uniprot_id} already exists (ID: {existing[0]})")
            return existing[0]
        
        # Fetch from UniProt
        print(f"📥 Fetching target data from UniProt: {uniprot_id}")
        uniprot_data = fetch_uniprot_target(uniprot_id)
        if not uniprot_data:
            print(f"⚠️  Could not fetch UniProt data for {uniprot_id}")
            return None
        
        # Fetch from IUPHAR if available
        iuphar_data = fetch_iuphar_target(uniprot_id)
        if iuphar_data and iuphar_data.get('ligand_types'):
            if ligand_types:
                ligand_types = list(set(ligand_types + iuphar_data['ligand_types']))
            else:
                ligand_types = iuphar_data['ligand_types']
        
        # Insert target
        cursor.execute("""
            INSERT INTO targets (uniprot_id, gene_symbol, protein_name, function,
                               cellular_location, cancer_role, ligand_types)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            uniprot_data['uniprot_id'],
            uniprot_data.get('gene_symbol'),
            uniprot_data.get('protein_name'),
            uniprot_data.get('function'),
            uniprot_data.get('cellular_location'),
            cancer_role,
            json.dumps(ligand_types) if ligand_types else None
        ))
        
        target_id = cursor.lastrowid
        conn.commit()
        print(f"✅ Loaded target {uniprot_id} (ID: {target_id})")
        return target_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading target {uniprot_id}: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def get_target_by_id(target_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict]:
    """
    Get target details by ID.
    
    Args:
        target_id: Target ID
        conn: Optional database connection
        
    Returns:
        Target dictionary or None
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            return None
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM targets WHERE id = ?", (target_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        columns = [d[0] for d in cursor.description]
        target = dict(zip(columns, row))
        
        # Parse JSON fields
        if target.get('ligand_types'):
            try:
                target['ligand_types'] = json.loads(target['ligand_types'])
            except (json.JSONDecodeError, TypeError):
                target['ligand_types'] = []
        
        return target
    finally:
        if should_close:
            conn.close()


def get_targets_for_mechanism(mechanism_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all targets for a mechanism.
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        List of target dictionaries
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
            SELECT t.*, mt.role_in_mechanism
            FROM targets t
            JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ?
            ORDER BY t.gene_symbol
        """, (mechanism_id,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        targets = []
        
        for row in rows:
            target = dict(zip(columns, row))
            # Parse JSON fields
            if target.get('ligand_types'):
                try:
                    target['ligand_types'] = json.loads(target['ligand_types'])
                except (json.JSONDecodeError, TypeError):
                    target['ligand_types'] = []
            targets.append(target)
        
        return targets
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # Test loading a target
    print("🧪 Testing target loader...")
    target_id = load_target_from_uniprot('P21589', cancer_role='Overexpressed in many cancers')
    if target_id:
        print(f"✅ Successfully loaded target (ID: {target_id})")
        
        # Test retrieval
        target = get_target_by_id(target_id)
        if target:
            print(f"✅ Retrieved target: {target.get('protein_name', 'Unknown')}")
