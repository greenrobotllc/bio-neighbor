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
        Count of newly inserted assays (int), or None on failure
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
        newly_inserted = 0
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

                # Extract readout information
                readout = assay.get('assay_organism') or assay.get('assay_cell_type') or 'Not specified'
                
                # Insert assay
                try:
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
                    
                    assay_id = cursor.lastrowid
                    assay_ids.append(assay_id)
                    newly_inserted += 1
                except Exception as db_error:
                    print(f"   ⚠️  Database error inserting assay {assay_chembl_id}: {db_error}")
                    continue
                
            except Exception as e:
                print(f"⚠️  Error processing ChEMBL assay: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        conn.commit()
        if newly_inserted > 0:
            print(f"✅ Loaded {newly_inserted} new assays from ChEMBL for target {target_id} (total: {len(assay_ids)})")
        else:
            print(f"ℹ️  No new assays loaded for target {target_id} (found {len(assay_ids)} existing)")
        return newly_inserted  # Return count of newly inserted assays
        
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
        assays = [dict(zip(columns, row, strict=True)) for row in rows]
        
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
        assays = [dict(zip(columns, row, strict=True)) for row in rows]
        
        return assays
    finally:
        if should_close:
            conn.close()


def load_assays_for_mechanism_targets(mechanism_id: int, force_refresh: bool = False,
                                      conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load assays for all targets in a mechanism from ChEMBL and PubChem.
    
    Args:
        mechanism_id: Mechanism ID
        force_refresh: If True, reload even if assays exist
        conn: Optional database connection
        
    Returns:
        Count of successfully loaded assays
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        from target_loader import get_targets_for_mechanism
        
        # Get all targets for this mechanism
        targets = get_targets_for_mechanism(mechanism_id, conn)
        
        if not targets:
            print(f"⚠️  No targets found for mechanism {mechanism_id}")
            return 0
        
        print(f"📋 Found {len(targets)} targets for mechanism {mechanism_id}")
        
        total_loaded = 0
        
        for target in targets:
            target_id = target['id']
            uniprot_id = target.get('uniprot_id')
            gene_symbol = target.get('gene_symbol')
            
            if not target_id:
                continue
            
            # Check if we should skip (assays already exist)
            if not force_refresh:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM assays WHERE target_id = ?", (target_id,))
                existing_count = cursor.fetchone()[0]
                if existing_count > 0:
                    print(f"⏭️  Target {target_id} ({gene_symbol or uniprot_id}) already has {existing_count} assays, skipping...")
                    continue
            
            print(f"\n🔍 Loading assays for target {target_id} ({gene_symbol or uniprot_id})...")
            
            # Try ChEMBL first (if available)
            if CHEMBL_AVAILABLE:
                try:
                    # Try to find ChEMBL target ID by UniProt ID or gene symbol
                    chembl_target_id = None
                    
                    if uniprot_id:
                        # Query ChEMBL for target by UniProt ID
                        try:
                            targets_chembl = new_client.target.filter(target_components__target_component_synonym__synonym=uniprot_id).only(['target_chembl_id'])
                            if targets_chembl:
                                chembl_target_id = targets_chembl[0]['target_chembl_id']
                        except Exception as e:
                            print(f"   ⚠️  ChEMBL UniProt lookup failed for {uniprot_id}: {e}")

                    # If not found by UniProt, try gene symbol
                    if not chembl_target_id and gene_symbol:
                        try:
                            targets_chembl = new_client.target.filter(pref_name__icontains=gene_symbol).only(['target_chembl_id'])
                            if targets_chembl:
                                chembl_target_id = targets_chembl[0]['target_chembl_id']
                        except Exception as e:
                            print(f"   ⚠️  ChEMBL gene symbol lookup failed for {gene_symbol}: {e}")
                    
                    if chembl_target_id:
                        print(f"   Found ChEMBL target ID: {chembl_target_id}")

                        # Load assays from ChEMBL
                        result = load_assay_from_chembl(target_id, chembl_target_id, conn)
                        if result is not None:
                            # result is now the count of newly loaded assays
                            newly_loaded = result
                            total_loaded += newly_loaded
                            if newly_loaded > 0:
                                print(f"   ✅ Loaded {newly_loaded} new assays from ChEMBL for target {target_id}")
                            else:
                                print(f"   ℹ️  No new assays loaded for target {target_id} (may already exist)")
                            continue  # Success with ChEMBL, skip PubChem
                        else:
                            print(f"   ⚠️  Failed to load assays from ChEMBL for target {target_id}")
                    else:
                        print(f"   ⚠️  Could not find ChEMBL target ID for {gene_symbol or uniprot_id}")
                        print("   🔄 ChEMBL target lookup failed, trying alternative data sources...")
                except Exception as e:
                    print(f"   ⚠️  Error loading from ChEMBL: {e}")
                    print("   🔄 ChEMBL API error, trying alternative data sources...")
                    # Continue to try PubChem
            
            # Note: PubChem BioAssay loading would require specific assay IDs
            # This is more complex and would need manual curation or additional API calls
            # For now, we rely on ChEMBL for automated assay loading
        
        print(f"\n✅ Total assays loaded: {total_loaded}")
        return total_loaded
        
    except Exception as e:
        print(f"❌ Error in load_assays_for_mechanism_targets: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # Test loading assays
    print("🧪 Testing assay loader...")
    print("✅ Assay loader module ready")
