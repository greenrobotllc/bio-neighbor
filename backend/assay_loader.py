"""
Assay loader for cancer mechanism research.
Loads assay data from PubChem BioAssay and ChEMBL.
"""

import sqlite3
import json
import requests
import time
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

try:
    from chembl_webresource_client.new_client import new_client
    CHEMBL_AVAILABLE = True
except ImportError:
    CHEMBL_AVAILABLE = False
    new_client = None

# PubChem BioAssay API
PUBCHEM_ASSAY_API = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/assay"


def load_assay_from_chembl(target_id: int, chembl_target_id: str,
                           conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load assays from ChEMBL for a target.
    
    Args:
        target_id: Target ID in database
        chembl_target_id: ChEMBL target ID
        conn: Optional database connection
        
    Returns:
        Assay ID if successful, None otherwise
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
        
        print(f"📥 Fetching assays from ChEMBL for target {chembl_target_id}")
        
        try:
            assays = new_client.assay.filter(
                target_chembl_id=chembl_target_id,
                limit=50  # Limit for MVP
            )
        except Exception as e:
            print(f"⚠️  Error querying ChEMBL assays: {e}")
            return None
        
        assay_ids = []
        for assay in assays:
            try:
                assay_chembl_id = assay.get('assay_chembl_id')
                if not assay_chembl_id:
                    continue
                
                # Check if assay already exists
                cursor.execute("""
                    SELECT id FROM assays 
                    WHERE chembl_assay_id = ? AND target_id = ?
                """, (assay_chembl_id, target_id))
                existing = cursor.fetchone()
                if existing:
                    assay_ids.append(existing[0])
                    continue
                
                assay_type = assay.get('assay_type', 'Unknown')
                assay_description = assay.get('assay_description', '')
                
                # Extract readout information
                readout = assay.get('assay_organism') or assay.get('assay_cell_type') or 'Not specified'
                
                # Insert assay
                cursor.execute("""
                    INSERT INTO assays (assay_type, target_id, readout, limitations,
                                     data_source, chembl_assay_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    assay_type,
                    target_id,
                    readout,
                    None,  # Limitations not directly available from ChEMBL API
                    'ChEMBL',
                    assay_chembl_id
                ))
                
                assay_ids.append(cursor.lastrowid)
                
            except Exception as e:
                print(f"⚠️  Error processing ChEMBL assay: {e}")
                continue
        
        conn.commit()
        print(f"✅ Loaded {len(assay_ids)} assays from ChEMBL for target {target_id}")
        return assay_ids[0] if assay_ids else None
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading assays from ChEMBL: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def load_assay_from_pubchem(target_id: int, pubchem_assay_id: str,
                            conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load assay from PubChem BioAssay.
    
    Args:
        target_id: Target ID in database
        pubchem_assay_id: PubChem Assay ID
        conn: Optional database connection
        
    Returns:
        Assay ID if successful, None otherwise
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Check if assay already exists
        cursor.execute("""
            SELECT id FROM assays 
            WHERE pubchem_assay_id = ? AND target_id = ?
        """, (pubchem_assay_id, target_id))
        existing = cursor.fetchone()
        if existing:
            return existing[0]
        
        print(f"📥 Fetching assay from PubChem: {pubchem_assay_id}")
        
        try:
            # PubChem BioAssay REST API
            url = f"{PUBCHEM_ASSAY_API}/aid/{pubchem_assay_id}/JSON"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract assay information
            pc_assay = data.get('PC_AssayContainer', [{}])[0]
            assay_info = pc_assay.get('assay', {})
            
            assay_type = assay_info.get('name', {}).get('string', 'Unknown')
            description = assay_info.get('description', {}).get('string', '')
            
            # Extract readout
            readout = description[:200] if description else 'Not specified'
            
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Error fetching PubChem assay {pubchem_assay_id}: {e}")
            return None
        except Exception as e:
            print(f"⚠️  Error parsing PubChem assay {pubchem_assay_id}: {e}")
            return None
        
        # Insert assay
        cursor.execute("""
            INSERT INTO assays (assay_type, target_id, readout, limitations,
                             data_source, pubchem_assay_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            assay_type,
            target_id,
            readout,
            None,  # Limitations not directly available
            'PubChem BioAssay',
            pubchem_assay_id
        ))
        
        assay_id = cursor.lastrowid
        conn.commit()
        print(f"✅ Loaded assay from PubChem (ID: {assay_id})")
        return assay_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading assay from PubChem: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def get_assays_for_target(target_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all assays for a target.
    
    Args:
        target_id: Target ID
        conn: Optional database connection
        
    Returns:
        List of assay dictionaries
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
            SELECT * FROM assays
            WHERE target_id = ?
            ORDER BY assay_type
        """, (target_id,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        assays = [dict(zip(columns, row)) for row in rows]
        
        return assays
    finally:
        if should_close:
            conn.close()


def get_assays_for_mechanism(mechanism_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all assays for a mechanism (across all targets).
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        List of assay dictionaries
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
            SELECT DISTINCT a.*
            FROM assays a
            JOIN targets t ON a.target_id = t.id
            JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ?
            ORDER BY a.assay_type
        """, (mechanism_id,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        assays = [dict(zip(columns, row)) for row in rows]
        
        return assays
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # Test loading assays
    print("🧪 Testing assay loader...")
    print("✅ Assay loader module ready")
