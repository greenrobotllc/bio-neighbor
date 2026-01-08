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


def test_chembl_connectivity(timeout: int = 5) -> bool:
    """
    Test if ChEMBL API is accessible.
    
    Args:
        timeout: Timeout in seconds for the test query
    
    Returns:
        True if ChEMBL is accessible, False otherwise
    """
    if not CHEMBL_AVAILABLE:
        print("⚠️  ChEMBL client not available (package not installed)")
        return False
    
    try:
        import time
        start_time = time.time()
        # Try a simple query that should always work - query for a well-known target
        test_target = new_client.target.filter(target_chembl_id='CHEMBL25').only(['target_chembl_id'])
        result = list(test_target)[:1]  # Force evaluation, limit to 1 result
        elapsed = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        if result:
            print(f"✅ ChEMBL API connectivity test passed ({elapsed:.0f}ms)")
            return True
        else:
            print("⚠️  ChEMBL API returned empty result")
            return False
    except Exception as e:
        print(f"⚠️  ChEMBL API connectivity test failed: {e}")
        return False


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
        newly_inserted = 0
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
                except Exception as e:
                    print(f"   ⚠️  Could not fetch molecule {molecule_chembl_id} from ChEMBL: {e}")
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
                try:
                    cursor.execute("""
                        INSERT INTO ligands (name, smiles, chembl_id, interaction_type, target_id, molecule_index)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (name, smiles, molecule_chembl_id, interaction_type, target_id, molecule_index))
                    
                    ligand_id = cursor.lastrowid
                    ligand_ids.append(ligand_id)
                    newly_inserted += 1
                except sqlite3.IntegrityError as e:
                    print(f"   ⚠️  Database error inserting ligand {molecule_chembl_id}: {e}")
                    continue
                
            except Exception as e:
                print(f"⚠️  Error processing ChEMBL activity: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        conn.commit()
        if newly_inserted > 0:
            print(f"✅ Loaded {newly_inserted} new ligands from ChEMBL for target {target_id} (total: {len(ligand_ids)})")
        else:
            print(f"ℹ️  No new ligands loaded for target {target_id} (found {len(ligand_ids)} existing)")
        return newly_inserted  # Return count of newly inserted ligands
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading ligands from ChEMBL: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def load_ligands_from_iuphar(target_id: int, uniprot_id: Optional[str] = None,
                             interaction_type: str = 'inhibitor',
                             conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load ligands from IUPHAR Guide to Pharmacology by UniProt ID.
    
    IUPHAR provides curated ligand-target interactions with quantitative data.
    
    Args:
        target_id: Target ID in database
        uniprot_id: UniProt ID to search for
        interaction_type: Type of interaction (will be determined from IUPHAR data)
        conn: Optional database connection
    
    Returns:
        Count of newly loaded ligands
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        newly_inserted = 0
        
        if not uniprot_id:
            print("   ⚠️  No UniProt ID provided for IUPHAR search")
            return 0
        
        print(f"   📥 Searching IUPHAR for target: {uniprot_id}")
        
        # IUPHAR Guide to Pharmacology API
        IUPHAR_API_BASE = "https://www.guidetopharmacology.org/services"
        
        try:
            time.sleep(1.0)  # Rate limiting for IUPHAR (1 req/sec recommended)
            
            # First, get all targets from IUPHAR and filter by UniProt ID
            # IUPHAR API doesn't support query parameters, so we fetch all and filter
            targets_url = f"{IUPHAR_API_BASE}/targets.json"
            response = requests.get(targets_url, timeout=10)
            
            if response.status_code == 200:
                targets_data = response.json()
                
                # Find target by UniProt ID
                iuphar_target = None
                for target in targets_data:
                    # Check both 'uniprot' and 'uniprotId' fields
                    target_uniprot = target.get('uniprot') or target.get('uniprotId')
                    if target_uniprot == uniprot_id:
                        iuphar_target = target
                        break
                
                if not iuphar_target:
                    print(f"   ⚠️  Target not found in IUPHAR for UniProt ID {uniprot_id}")
                    return 0
                
                iuphar_target_id = iuphar_target.get('targetId')
                if not iuphar_target_id:
                    print(f"   ⚠️  No IUPHAR target ID found")
                    return 0
                
                # Get ligands for this target
                ligands_url = f"{IUPHAR_API_BASE}/ligands.json?target_id={iuphar_target_id}"
                time.sleep(1.0)  # Rate limiting
                ligands_response = requests.get(ligands_url, timeout=10)
                
                if ligands_response.status_code == 200:
                    ligands_data = ligands_response.json()
                    
                    for ligand_data in ligands_data[:50]:  # Limit to top 50
                        try:
                            ligand_name = ligand_data.get('name', '')
                            ligand_id = ligand_data.get('ligandId')
                            
                            if not ligand_name or not ligand_id:
                                continue
                            
                            # Check if ligand already exists
                            cursor.execute("""
                                SELECT id FROM ligands 
                                WHERE name = ? AND target_id = ?
                            """, (ligand_name, target_id))
                            if cursor.fetchone():
                                continue
                            
                            # Get interaction type from IUPHAR data
                            interaction = ligand_data.get('type', interaction_type)
                            # Map IUPHAR types to our types
                            if 'agonist' in interaction.lower():
                                interaction = 'agonist'
                            elif 'antagonist' in interaction.lower():
                                interaction = 'antagonist'
                            else:
                                interaction = interaction_type
                            
                            # Try to get SMILES from IUPHAR or PubChem
                            smiles = None
                            pubchem_cid = None
                            
                            # IUPHAR may have PubChem CID
                            if 'pubchemCid' in ligand_data:
                                pubchem_cid = str(ligand_data['pubchemCid'])
                                # Try to get SMILES from PubChem
                                if PUBCHEM_AVAILABLE:
                                    try:
                                        compound = pcp.Compound.from_cid(int(pubchem_cid))
                                        smiles = compound.canonical_smiles
                                        time.sleep(0.2)  # Rate limiting
                                    except Exception:
                                        pass
                            
                            # Find molecule in database
                            molecule_index = None
                            if pubchem_cid:
                                molecule_index = find_molecule_by_pubchem_cid(pubchem_cid, conn)
                            if not molecule_index and smiles:
                                molecule_index = find_molecule_by_smiles(smiles, conn)
                            
                            # Insert ligand
                            try:
                                cursor.execute("""
                                    INSERT INTO ligands (name, smiles, pubchem_cid, interaction_type, target_id, molecule_index)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (ligand_name, smiles, pubchem_cid, interaction, target_id, molecule_index))
                                newly_inserted += 1
                            except sqlite3.IntegrityError:
                                continue
                        except Exception as e:
                            print(f"   ⚠️  Error processing IUPHAR ligand: {e}")
                            continue
                    
                    conn.commit()
                    if newly_inserted > 0:
                        print(f"   ✅ Loaded {newly_inserted} ligands from IUPHAR for target {target_id}")
                    else:
                        print(f"   ℹ️  No new ligands found in IUPHAR for {uniprot_id}")
                else:
                    print(f"   ⚠️  IUPHAR ligands API returned status {ligands_response.status_code}")
            else:
                print(f"   ⚠️  IUPHAR targets API returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  IUPHAR API not accessible: {e}")
        except Exception as e:
            print(f"   ⚠️  Error querying IUPHAR: {e}")
            import traceback
            traceback.print_exc()
        
        return newly_inserted
        
    except Exception as e:
        print(f"   ❌ Error loading ligands from IUPHAR: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        if should_close:
            conn.close()


def load_ligands_from_bindingdb(target_id: int, uniprot_id: Optional[str] = None,
                                gene_symbol: Optional[str] = None,
                                interaction_type: str = 'inhibitor',
                                conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load ligands from BindingDB by UniProt ID or gene symbol.
    
    BindingDB provides measured binding affinities. This function attempts to use
    BindingDB's REST API or local data if available.
    
    Args:
        target_id: Target ID in database
        uniprot_id: UniProt ID to search for
        gene_symbol: Gene symbol to search for
        interaction_type: Type of interaction
        conn: Optional database connection
    
    Returns:
        Count of newly loaded ligands
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        newly_inserted = 0
        
        if not uniprot_id and not gene_symbol:
            print("   ⚠️  No UniProt ID or gene symbol provided for BindingDB search")
            return 0
        
        print(f"   📥 Searching BindingDB for target: {uniprot_id or gene_symbol}")
        
        # BindingDB REST API endpoint
        # Note: BindingDB API may not be publicly available, so this is a placeholder
        # In practice, you might need to download BindingDB TSV files and create a local lookup
        
        try:
            # Try BindingDB API if available
            # Base URL: https://bindingdb.org/api
            # This is a placeholder - actual API endpoints may vary
            
            # For now, we'll use a simple HTTP request to check if BindingDB is accessible
            # and attempt to query it
            search_url = None
            if uniprot_id:
                # Try to query by UniProt ID
                search_url = f"https://bindingdb.org/api/v1/targets?uniprot={uniprot_id}"
            elif gene_symbol:
                # Try to query by gene symbol
                search_url = f"https://bindingdb.org/api/v1/targets?gene={gene_symbol}"
            
            if search_url:
                time.sleep(0.5)  # Rate limiting
                response = requests.get(search_url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    # Parse BindingDB response and extract ligands
                    # This is a placeholder - actual response format may vary
                    print(f"   ℹ️  BindingDB API responded (implementation needed for parsing)")
                    # TODO: Parse BindingDB response and extract ligand data
                else:
                    print(f"   ⚠️  BindingDB API returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  BindingDB API not accessible: {e}")
            print(f"   ℹ️  Consider downloading BindingDB TSV files for local lookup")
        except Exception as e:
            print(f"   ⚠️  Error querying BindingDB: {e}")
        
        return newly_inserted
        
    except Exception as e:
        print(f"   ❌ Error loading ligands from BindingDB: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        if should_close:
            conn.close()


def load_ligands_from_pubchem_bioassay(target_id: int, gene_symbol: Optional[str] = None,
                                       uniprot_id: Optional[str] = None,
                                       interaction_type: str = 'inhibitor',
                                       conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load ligands from PubChem BioAssay API by querying assays for a target.
    
    Args:
        target_id: Target ID in database
        gene_symbol: Gene symbol to search for
        uniprot_id: UniProt ID to search for
        interaction_type: Type of interaction
        conn: Optional database connection
    
    Returns:
        Count of newly loaded ligands
    """
    if not PUBCHEM_AVAILABLE:
        print("⚠️  PubChemPy not available")
        return 0
    
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        newly_inserted = 0
        
        # Try to find assays by gene symbol first
        search_term = None
        if gene_symbol:
            search_term = gene_symbol
        elif uniprot_id:
            search_term = uniprot_id
        
        if not search_term:
            print("   ⚠️  No gene symbol or UniProt ID provided for PubChem search")
            return 0
        
        print(f"   📥 Searching PubChem BioAssay for target: {search_term}")
        
        # PubChem BioAssay API - search by target/gene
        # Note: PubChem doesn't have direct gene/target search, so we'll use compound search
        # and filter by known drug names or use PubChem's text search
        
        # Alternative approach: Use PubChem's text search to find compounds
        # related to the target, then get their assay data
        try:
            # Search for compounds by name (using gene symbol as search term)
            # This is a simplified approach - in practice, you'd want to use
            # PubChem's more specific APIs
            time.sleep(0.2)  # Rate limiting for PubChem (5 req/sec = 200ms delay)
            
            # Try to find compounds using pubchempy
            try:
                compounds = pcp.get_compounds(search_term, 'name', as_dataframe=True)
            except Exception as e:
                print(f"   ⚠️  PubChem search failed: {e}")
                return 0
            
            if compounds is not None and len(compounds) > 0:
                # Limit to top 50 compounds
                # Note: In PubChem DataFrame, the index IS the CID
                for cid, row in compounds.head(50).iterrows():
                    try:
                        # CID is the DataFrame index
                        cid = str(cid)
                        
                        if not cid or cid == 'nan' or cid == 'None':
                            continue
                        
                        # Validate CID is numeric
                        try:
                            cid_int = int(cid)
                        except ValueError:
                            continue
                        
                        # Check if ligand already exists
                        cursor.execute("""
                            SELECT id FROM ligands 
                            WHERE pubchem_cid = ? AND target_id = ?
                        """, (cid, target_id))
                        if cursor.fetchone():
                            continue
                        
                        # Get compound details - use SMILES from DataFrame if available, otherwise fetch
                        try:
                            # Try to get SMILES from DataFrame first (faster)
                            smiles = row.get('smiles') or row.get('connectivity_smiles')
                            name = row.get('iupac_name') or f"PubChem_{cid}"
                            
                            # If no SMILES in DataFrame, fetch compound
                            if not smiles:
                                compound = pcp.Compound.from_cid(cid_int)
                                name = compound.iupac_name or (compound.synonyms[0] if compound.synonyms else name)
                                smiles = compound.canonical_smiles
                                time.sleep(0.2)  # Rate limiting
                        except Exception as e:
                            print(f"   ⚠️  Error fetching PubChem compound {cid}: {e}")
                            continue
                        
                        # Find molecule in database
                        molecule_index = find_molecule_by_pubchem_cid(cid, conn)
                        if not molecule_index and smiles:
                            molecule_index = find_molecule_by_smiles(smiles, conn)
                        
                        # Insert ligand
                        try:
                            cursor.execute("""
                                INSERT INTO ligands (name, smiles, pubchem_cid, interaction_type, target_id, molecule_index)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (name, smiles, cid, interaction_type, target_id, molecule_index))
                            newly_inserted += 1
                        except sqlite3.IntegrityError:
                            continue
                        
                        # Rate limiting (only if we fetched compound details)
                        if not smiles or not name or name.startswith('PubChem_'):
                            time.sleep(0.2)
                    except Exception as e:
                        print(f"   ⚠️  Error processing PubChem compound: {e}")
                        continue
                
                conn.commit()
                if newly_inserted > 0:
                    print(f"   ✅ Loaded {newly_inserted} ligands from PubChem BioAssay for target {target_id}")
                else:
                    print(f"   ℹ️  No new ligands found in PubChem for {search_term}")
            else:
                print(f"   ⚠️  No compounds found in PubChem for {search_term}")
        except Exception as e:
            print(f"   ⚠️  Error querying PubChem BioAssay: {e}")
            return 0
        
        return newly_inserted
        
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error loading ligands from PubChem: {e}")
        import traceback
        traceback.print_exc()
        return 0
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


def load_ligands_for_mechanism_targets(mechanism_id: int, force_refresh: bool = False,
                                       conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load ligands for all targets in a mechanism from ChEMBL and PubChem.
    
    Args:
        mechanism_id: Mechanism ID
        force_refresh: If True, reload even if ligands exist
        conn: Optional database connection
        
    Returns:
        Count of successfully loaded ligands
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
            
            # Check if we should skip (ligands already exist)
            if not force_refresh:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM ligands WHERE target_id = ?", (target_id,))
                existing_count = cursor.fetchone()[0]
                if existing_count > 0:
                    print(f"⏭️  Target {target_id} ({gene_symbol or uniprot_id}) already has {existing_count} ligands, skipping...")
                    continue
            
            print(f"\n🔍 Loading ligands for target {target_id} ({gene_symbol or uniprot_id})...")
            
            # Determine interaction type from ligand_types (needed for all data sources)
            ligand_types = target.get('ligand_types', [])
            interaction_type = 'inhibitor'  # default
            if ligand_types:
                if isinstance(ligand_types, str):
                    import json
                    try:
                        ligand_types = json.loads(ligand_types)
                    except:
                        ligand_types = []
                if 'antagonist' in ligand_types:
                    interaction_type = 'antagonist'
                elif 'agonist' in ligand_types:
                    interaction_type = 'agonist'
            
            # Test ChEMBL connectivity first
            chembl_available = test_chembl_connectivity()
            
            # Try ChEMBL first (if available and accessible)
            if CHEMBL_AVAILABLE and chembl_available:
                try:
                    # Try to find ChEMBL target ID by UniProt ID or gene symbol
                    chembl_target_id = None
                    
                    if uniprot_id:
                        # Query ChEMBL for target by UniProt ID
                        try:
                            targets_chembl = new_client.target.filter(target_components__target_component_synonym__synonym=uniprot_id).only(['target_chembl_id'])
                            if targets_chembl:
                                chembl_target_id = targets_chembl[0]['target_chembl_id']
                        except Exception:
                            pass
                    
                    # If not found by UniProt, try gene symbol
                    if not chembl_target_id and gene_symbol:
                        try:
                            targets_chembl = new_client.target.filter(pref_name__icontains=gene_symbol).only(['target_chembl_id'])
                            if targets_chembl:
                                chembl_target_id = targets_chembl[0]['target_chembl_id']
                        except Exception:
                            pass
                    
                    if chembl_target_id:
                        print(f"   Found ChEMBL target ID: {chembl_target_id}")
                        # Get count before loading
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM ligands WHERE target_id = ?", (target_id,))
                        count_before = cursor.fetchone()[0]
                        
                        # Load ligands from ChEMBL
                        result = load_ligand_from_chembl(target_id, chembl_target_id, interaction_type, conn)
                        if result is not None:
                            # result is now the count of newly loaded ligands
                            newly_loaded = result
                            total_loaded += newly_loaded
                            if newly_loaded > 0:
                                print(f"   ✅ Loaded {newly_loaded} new ligands from ChEMBL for target {target_id}")
                            else:
                                print(f"   ℹ️  No new ligands loaded for target {target_id} (may already exist)")
                            continue  # Success with ChEMBL, skip PubChem
                        else:
                            print(f"   ⚠️  Failed to load ligands from ChEMBL for target {target_id}")
                    else:
                        print(f"   ⚠️  Could not find ChEMBL target ID for {gene_symbol or uniprot_id}")
                        print(f"   🔄 ChEMBL target lookup failed, trying alternative data sources...")
                except Exception as e:
                    print(f"   ⚠️  Error loading from ChEMBL: {e}")
                    print(f"   🔄 ChEMBL API error, trying alternative data sources...")
                    # Continue to try PubChem
            
            # Fallback chain: PubChem -> BindingDB -> IUPHAR
            ligands_loaded_from_source = None
            result = None  # Initialize result for fallback check
            
            # Try PubChem if ChEMBL failed or unavailable
            if PUBCHEM_AVAILABLE and (not chembl_available or result is None or result == 0):
                print(f"   🔄 ChEMBL unavailable or failed, trying PubChem BioAssay...")
                try:
                    pubchem_result = load_ligands_from_pubchem_bioassay(
                        target_id=target_id,
                        gene_symbol=gene_symbol,
                        uniprot_id=uniprot_id,
                        interaction_type=interaction_type,
                        conn=conn
                    )
                    if pubchem_result and pubchem_result > 0:
                        total_loaded += pubchem_result
                        ligands_loaded_from_source = "PubChem"
                        print(f"   ✅ Loaded {pubchem_result} ligands from PubChem for target {target_id}")
                except Exception as e:
                    print(f"   ⚠️  Error with PubChem: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Try BindingDB if still no ligands
            if ligands_loaded_from_source is None and uniprot_id:
                print(f"   🔄 Trying BindingDB...")
                try:
                    bindingdb_result = load_ligands_from_bindingdb(
                        target_id=target_id,
                        uniprot_id=uniprot_id,
                        gene_symbol=gene_symbol,
                        interaction_type=interaction_type,  # Now defined above
                        conn=conn
                    )
                    if bindingdb_result and bindingdb_result > 0:
                        total_loaded += bindingdb_result
                        ligands_loaded_from_source = "BindingDB"
                        print(f"   ✅ Loaded {bindingdb_result} ligands from BindingDB for target {target_id}")
                except Exception as e:
                    print(f"   ⚠️  Error with BindingDB: {e}")
            
            # Try IUPHAR as final fallback
            if ligands_loaded_from_source is None and uniprot_id:
                print(f"   🔄 Trying IUPHAR Guide to Pharmacology...")
                try:
                    iuphar_result = load_ligands_from_iuphar(
                        target_id=target_id,
                        uniprot_id=uniprot_id,
                        interaction_type=interaction_type,  # Now defined above
                        conn=conn
                    )
                    if iuphar_result and iuphar_result > 0:
                        total_loaded += iuphar_result
                        ligands_loaded_from_source = "IUPHAR"
                        print(f"   ✅ Loaded {iuphar_result} ligands from IUPHAR for target {target_id}")
                except Exception as e:
                    print(f"   ⚠️  Error with IUPHAR: {e}")
            
            # Final fallback: Try curated ligands if no other source worked
            if ligands_loaded_from_source is None:
                print(f"   🔄 Trying curated ligand lists...")
                try:
                    from curated_ligand_loader import load_curated_ligands_for_target
                    from target_loader import get_targets_for_mechanism
                    
                    # Get mechanism name for curated list selection
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM mechanisms WHERE id = ?", (mechanism_id,))
                    mechanism_result = cursor.fetchone()
                    mechanism_name = mechanism_result[0] if mechanism_result else ""
                    
                    curated_result = load_curated_ligands_for_target(
                        target_id, gene_symbol, mechanism_name, conn
                    )
                    if curated_result and curated_result > 0:
                        total_loaded += curated_result
                        ligands_loaded_from_source = "Curated"
                        print(f"   ✅ Loaded {curated_result} curated ligands for target {target_id}")
                except Exception as e:
                    print(f"   ⚠️  Error loading curated ligands: {e}")
            
            # Final message if no ligands loaded
            if ligands_loaded_from_source is None:
                print(f"   ⚠️  No ligands loaded from any data source for target {target_id}")
                print(f"   ℹ️  All data sources (ChEMBL, PubChem, BindingDB, IUPHAR, Curated) unavailable or returned no results")
        
        print(f"\n✅ Total ligands loaded: {total_loaded}")
        return total_loaded
        
    except Exception as e:
        print(f"❌ Error in load_ligands_for_mechanism_targets: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # Test loading ligands
    print("🧪 Testing ligand loader...")
    # This would require a target_id and ChEMBL target ID
    # For testing, we'd need to set up a target first
    print("✅ Ligand loader module ready")
