"""
PD-1/PD-L1 mechanism loader for BioNeighbor.
Loads PD-1/PD-L1 immune checkpoint mechanism definition and initial data.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

# PD-1/PD-L1 Immune Checkpoint mechanism definition
PD1_PDL1_MECHANISM = {
    'name': 'PD-1/PD-L1 Immune Checkpoint',
    'description': 'Mechanism by which PD-1/PD-L1 signaling suppresses T cell activation, enabling tumor immune evasion',
    'biological_summary': '''The PD-1/PD-L1 pathway is a critical immune checkpoint that regulates T cell activation and 
tolerance. Programmed cell death protein 1 (PD-1) is expressed on activated T cells, B cells, and NK cells. Its ligands, 
PD-L1 (CD274) and PD-L2 (CD279), are expressed on tumor cells, antigen-presenting cells, and various tissues. When PD-1 
binds to PD-L1 or PD-L2, it delivers inhibitory signals that suppress T cell proliferation, cytokine production, and 
cytotoxic activity, leading to T cell exhaustion and enabling tumor immune evasion.''',
    'tumor_microenvironment_role': '''Tumor cells frequently upregulate PD-L1 expression as a mechanism of immune evasion. 
This creates an immunosuppressive microenvironment where tumor-infiltrating T cells become exhausted and unable to mount 
effective anti-tumor responses. The PD-1/PD-L1 axis is particularly important in cancers with high mutational burden 
and strong T cell infiltration, where blocking this pathway can restore anti-tumor immunity.''',
    'immune_effects': '''PD-1/PD-L1 signaling effects:
- Suppresses T cell activation and proliferation
- Reduces cytokine production (IFN-γ, IL-2, TNF-α)
- Promotes T cell exhaustion and anergy
- Inhibits cytotoxic T cell function
- Enhances regulatory T cell suppressive activity
- Reduces B cell activation and antibody production''',
    'data_sources': json.dumps([
        'UniProt',
        'IUPHAR Guide to Pharmacology',
        'ChEMBL',
        'PubChem',
        'Clinical trial databases',
        'Literature curation'
    ])
}

# Target definitions for PD-1/PD-L1 mechanism
PD1_PDL1_TARGETS = [
    {
        'uniprot_id': 'Q15116',
        'gene_symbol': 'PDCD1',
        'protein_name': 'Programmed cell death protein 1',
        'common_name': 'PD-1',
        'function': 'Immune checkpoint receptor that binds PD-L1 and PD-L2. Delivers inhibitory signals to T cells upon ligand binding, suppressing T cell activation and promoting exhaustion.',
        'cellular_location': 'Cell membrane',
        'cancer_role': 'Expressed on tumor-infiltrating T cells. High PD-1 expression correlates with T cell exhaustion and poor anti-tumor responses. Blocking PD-1 restores T cell function.',
        'ligand_types': json.dumps(['antagonist', 'inhibitor']),
        'role_in_mechanism': 'Primary receptor mediating immune checkpoint suppression'
    },
    {
        'uniprot_id': 'Q9NZQ7',
        'gene_symbol': 'CD274',
        'protein_name': 'Programmed death-ligand 1',
        'common_name': 'PD-L1',
        'function': 'Ligand for PD-1 receptor. Binds PD-1 with high affinity to deliver inhibitory signals to T cells, suppressing immune responses.',
        'cellular_location': 'Cell membrane, can be secreted',
        'cancer_role': 'Frequently overexpressed on tumor cells and tumor-associated immune cells. High PD-L1 expression is associated with immune evasion and poor prognosis in many cancers.',
        'ligand_types': json.dumps(['inhibitor', 'antagonist']),
        'role_in_mechanism': 'Primary ligand that binds PD-1 to suppress T cell activation'
    },
    {
        'uniprot_id': 'Q9BQ51',
        'gene_symbol': 'CD279',
        'protein_name': 'Programmed death-ligand 2',
        'common_name': 'PD-L2',
        'function': 'Alternative ligand for PD-1 receptor. Binds PD-1 with higher affinity than PD-L1 but has more restricted expression patterns.',
        'cellular_location': 'Cell membrane',
        'cancer_role': 'Expressed on some tumor cells and antigen-presenting cells. Less commonly targeted than PD-L1 but contributes to immune suppression.',
        'ligand_types': json.dumps(['inhibitor', 'antagonist']),
        'role_in_mechanism': 'Secondary ligand for PD-1 signaling in immune suppression'
    }
]


def load_pd1_pdl1_mechanism(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load the PD-1/PD-L1 immune checkpoint mechanism into the database.
    
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
        cursor.execute("SELECT id FROM mechanisms WHERE name = ?", (PD1_PDL1_MECHANISM['name'],))
        existing = cursor.fetchone()
        if existing:
            print(f"✅ Mechanism '{PD1_PDL1_MECHANISM['name']}' already exists (ID: {existing[0]})")
            return existing[0]
        
        # Insert mechanism
        cursor.execute("""
            INSERT INTO mechanisms (name, description, biological_summary, 
                                  tumor_microenvironment_role, immune_effects, data_sources)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            PD1_PDL1_MECHANISM['name'],
            PD1_PDL1_MECHANISM['description'],
            PD1_PDL1_MECHANISM['biological_summary'],
            PD1_PDL1_MECHANISM['tumor_microenvironment_role'],
            PD1_PDL1_MECHANISM['immune_effects'],
            PD1_PDL1_MECHANISM['data_sources']
        ))
        mechanism_id = cursor.lastrowid
        
        # Insert targets and link to mechanism
        for target_data in PD1_PDL1_TARGETS:
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
        print(f"✅ Loaded PD-1/PD-L1 mechanism (ID: {mechanism_id}) with {len(PD1_PDL1_TARGETS)} targets")
        return mechanism_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading PD-1/PD-L1 mechanism: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def load_pd1_pdl1_with_mappings(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load PD-1/PD-L1 mechanism and its cancer mappings.
    
    Args:
        conn: Optional database connection
        
    Returns:
        Mechanism ID if successful, None otherwise
    """
    mechanism_id = load_pd1_pdl1_mechanism(conn)
    if mechanism_id:
        try:
            from cancer_mapping_loader import load_pd1_pdl1_cancer_mappings
            load_pd1_pdl1_cancer_mappings(mechanism_id, conn)
        except Exception as e:
            print(f"⚠️  Warning: Could not load cancer mappings: {e}")
    return mechanism_id


if __name__ == "__main__":
    # Test loading the PD-1/PD-L1 mechanism
    print("🧪 Testing PD-1/PD-L1 mechanism loader...")
    mechanism_id = load_pd1_pdl1_mechanism()
    if mechanism_id:
        print(f"✅ Successfully loaded mechanism (ID: {mechanism_id})")
    else:
        print("❌ Failed to load mechanism")
