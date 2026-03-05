"""
Cancer mechanism loader for BioNeighbor.
Loads mechanism definitions and initial data for cancer research workspace.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

# Adenosine-Mediated Immune Suppression mechanism definition
ADENOSINE_MECHANISM = {
    'name': 'Adenosine-Mediated Immune Suppression',
    'description': 'Mechanism by which adenosine signaling suppresses immune responses in the tumor microenvironment',
    'biological_summary': '''Adenosine-mediated immune suppression is a critical mechanism in cancer progression. 
Tumor cells and immune cells in the tumor microenvironment produce adenosine through the sequential action of 
CD39 (ENTPD1) and CD73 (NT5E), which convert ATP/ADP to AMP and then to adenosine. Adenosine then binds to 
A2A and A2B receptors on immune cells, leading to suppression of T cell, NK cell, and macrophage function, 
thereby enabling immune evasion by tumors.''',
    'tumor_microenvironment_role': '''Adenosine accumulates in the hypoxic tumor microenvironment where ATP is 
released from dying cells. The CD39/CD73 pathway converts this ATP to adenosine, creating an immunosuppressive 
milieu. This mechanism is particularly active in solid tumors with high metabolic activity and hypoxia.''',
    'immune_effects': '''Adenosine signaling through A2A and A2B receptors:
- Suppresses T cell activation and proliferation
- Inhibits NK cell cytotoxicity
- Promotes regulatory T cell function
- Reduces macrophage pro-inflammatory responses
- Enhances myeloid-derived suppressor cell activity''',
    'data_sources': json.dumps([
        'UniProt',
        'IUPHAR Guide to Pharmacology',
        'ChEMBL',
        'PubChem',
        'Reactome',
        'Literature curation'
    ])
}

# Target definitions for adenosine mechanism
ADENOSINE_TARGETS = [
    {
        'uniprot_id': 'P21589',
        'gene_symbol': 'NT5E',
        'protein_name': '5\'-nucleotidase',
        'common_name': 'CD73',
        'function': 'Catalyzes the conversion of AMP to adenosine. Plays a key role in the adenosine pathway by producing extracellular adenosine.',
        'cellular_location': 'Cell membrane, extracellular',
        'cancer_role': 'Overexpressed in many cancers. High CD73 expression correlates with poor prognosis and immune suppression.',
        'ligand_types': json.dumps(['inhibitor']),
        'role_in_mechanism': 'Final step in adenosine production from ATP'
    },
    {
        'uniprot_id': 'P49961',
        'gene_symbol': 'ENTPD1',
        'protein_name': 'Ectonucleoside triphosphate diphosphohydrolase 1',
        'common_name': 'CD39',
        'function': 'Catalyzes the conversion of ATP/ADP to AMP. First step in the adenosine production pathway.',
        'cellular_location': 'Cell membrane, extracellular',
        'cancer_role': 'Expressed on regulatory T cells and tumor-associated macrophages. Contributes to immunosuppressive microenvironment.',
        'ligand_types': json.dumps(['inhibitor']),
        'role_in_mechanism': 'Initial step in adenosine production from ATP'
    },
    {
        'uniprot_id': 'P29274',
        'gene_symbol': 'ADORA2A',
        'protein_name': 'Adenosine A2A receptor',
        'common_name': 'A2A receptor',
        'function': 'G-protein coupled receptor that binds adenosine. Activation leads to increased cAMP and suppression of immune cell function.',
        'cellular_location': 'Cell membrane',
        'cancer_role': 'Expressed on T cells, NK cells, and macrophages. Activation suppresses anti-tumor immune responses.',
        'ligand_types': json.dumps(['antagonist', 'agonist']),
        'role_in_mechanism': 'Primary receptor mediating adenosine-induced immune suppression'
    },
    {
        'uniprot_id': 'P29275',
        'gene_symbol': 'ADORA2B',
        'protein_name': 'Adenosine A2B receptor',
        'common_name': 'A2B receptor',
        'function': 'G-protein coupled receptor that binds adenosine with lower affinity than A2A. Also contributes to immune suppression.',
        'cellular_location': 'Cell membrane',
        'cancer_role': 'Expressed on immune cells and some tumor cells. Contributes to immunosuppressive signaling.',
        'ligand_types': json.dumps(['antagonist', 'agonist']),
        'role_in_mechanism': 'Secondary receptor for adenosine signaling in immune suppression'
    }
]


def load_adenosine_mechanism(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load the adenosine-mediated immune suppression mechanism into the database.
    
    Args:
        conn: Optional database connection (creates new if None)
        
    Returns:
        Mechanism ID if successful, None otherwise
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Check if mechanism already exists
        cursor.execute("SELECT id FROM mechanisms WHERE name = ?", (ADENOSINE_MECHANISM['name'],))
        existing = cursor.fetchone()
        if existing:
            print(f"✅ Mechanism '{ADENOSINE_MECHANISM['name']}' already exists (ID: {existing[0]})")
            return existing[0]
        
        # Insert mechanism
        cursor.execute("""
            INSERT INTO mechanisms (name, description, biological_summary, 
                                  tumor_microenvironment_role, immune_effects, data_sources)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            ADENOSINE_MECHANISM['name'],
            ADENOSINE_MECHANISM['description'],
            ADENOSINE_MECHANISM['biological_summary'],
            ADENOSINE_MECHANISM['tumor_microenvironment_role'],
            ADENOSINE_MECHANISM['immune_effects'],
            ADENOSINE_MECHANISM['data_sources']
        ))
        mechanism_id = cursor.lastrowid
        
        # Insert targets and link to mechanism
        for target_data in ADENOSINE_TARGETS:
            # Check if target already exists
            cursor.execute("SELECT id FROM targets WHERE uniprot_id = ?", (target_data['uniprot_id'],))
            existing_target = cursor.fetchone()
            
            if existing_target:
                target_id = existing_target[0]
            else:
                # Insert target
                cursor.execute("""
                    INSERT INTO targets (uniprot_id, gene_symbol, protein_name, function,
                                       cellular_location, cancer_role, ligand_types)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    target_data['uniprot_id'],
                    target_data['gene_symbol'],
                    target_data['protein_name'],
                    target_data['function'],
                    target_data['cellular_location'],
                    target_data['cancer_role'],
                    target_data['ligand_types']
                ))
                target_id = cursor.lastrowid
            
            # Link target to mechanism
            cursor.execute("""
                INSERT OR IGNORE INTO mechanism_targets (mechanism_id, target_id, role_in_mechanism)
                VALUES (?, ?, ?)
            """, (mechanism_id, target_id, target_data['role_in_mechanism']))
        
        conn.commit()
        print(f"✅ Loaded adenosine mechanism (ID: {mechanism_id}) with {len(ADENOSINE_TARGETS)} targets")
        return mechanism_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading adenosine mechanism: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def get_mechanism_by_id(mechanism_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict]:
    """
    Get mechanism details by ID.
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        Mechanism dictionary or None
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            return None
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM mechanisms WHERE id = ?", (mechanism_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        columns = [d[0] for d in cursor.description]
        mechanism = dict(zip(columns, row))
        
        # Parse JSON fields
        if mechanism.get('data_sources'):
            try:
                mechanism['data_sources'] = json.loads(mechanism['data_sources'])
            except (json.JSONDecodeError, TypeError):
                mechanism['data_sources'] = []
        
        return mechanism
    finally:
        if should_close:
            conn.close()


def get_all_mechanisms(conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all mechanisms.
    
    Args:
        conn: Optional database connection
        
    Returns:
        List of mechanism dictionaries
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            return []
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM mechanisms ORDER BY name")
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        mechanisms = []
        
        for row in rows:
            mechanism = dict(zip(columns, row))
            # Parse JSON fields
            if mechanism.get('data_sources'):
                try:
                    mechanism['data_sources'] = json.loads(mechanism['data_sources'])
                except (json.JSONDecodeError, TypeError):
                    mechanism['data_sources'] = []
            mechanisms.append(mechanism)
        
        return mechanisms
    finally:
        if should_close:
            conn.close()


def load_all_default_mechanisms(conn: Optional[sqlite3.Connection] = None, 
                                 load_data: bool = True) -> List[int]:
    """
    Load all default mechanisms (adenosine and PD-1/PD-L1).
    
    Args:
        conn: Optional database connection
        load_data: If True, trigger ETL to load all data for mechanisms
        
    Returns:
        List of mechanism IDs loaded
    """
    mechanism_ids = []
    
    # Load adenosine mechanism
    adenosine_id = load_adenosine_mechanism(conn)
    if adenosine_id:
        mechanism_ids.append(adenosine_id)
        # Trigger ETL if requested
        if load_data:
            try:
                from cancer_research_etl import load_mechanism_data
                print(f"\n🔄 Loading data for adenosine mechanism (ID: {adenosine_id})...")
                load_mechanism_data(adenosine_id, force_refresh=False, conn=conn)
            except Exception as e:
                print(f"⚠️  Error loading data for adenosine mechanism: {e}")
                import traceback
                traceback.print_exc()
    
    # Load PD-1/PD-L1 mechanism
    try:
        from pd1_pdl1_mechanism_loader import load_pd1_pdl1_with_mappings
        pd1_id = load_pd1_pdl1_with_mappings(conn)
        if pd1_id:
            mechanism_ids.append(pd1_id)
            print(f"✅ Loaded PD-1/PD-L1 mechanism (ID: {pd1_id})")
            # Trigger ETL if requested
            if load_data:
                try:
                    from cancer_research_etl import load_mechanism_data
                    print(f"\n🔄 Loading data for PD-1/PD-L1 mechanism (ID: {pd1_id})...")
                    load_mechanism_data(pd1_id, force_refresh=False, conn=conn)
                except Exception as e:
                    print(f"⚠️  Error loading data for PD-1/PD-L1 mechanism: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            print("⚠️  PD-1/PD-L1 mechanism loader returned None")
    except ImportError as e:
        print(f"⚠️  PD-1/PD-L1 mechanism loader not available: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"⚠️  Error loading PD-1/PD-L1 mechanism: {e}")
        import traceback
        traceback.print_exc()
    
    return mechanism_ids


if __name__ == "__main__":
    # Test loading all mechanisms
    print("🧪 Testing cancer mechanism loader...")
    mechanism_ids = load_all_default_mechanisms()
    print(f"✅ Loaded {len(mechanism_ids)} mechanisms")
    
    # List all mechanisms
    all_mechanisms = get_all_mechanisms()
    print(f"✅ Total mechanisms in database: {len(all_mechanisms)}")
    for mechanism in all_mechanisms:
        print(f"   - {mechanism['name']} (ID: {mechanism['id']})")
