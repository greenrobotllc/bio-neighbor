"""
Drug outcome loader for cancer mechanism research.
Curates and classifies drug outcomes (partial success, failure, mixed).
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

# Curated drug outcomes for adenosine mechanism
# This is a starting point - in production, this would be expanded with literature mining
ADENOSINE_DRUG_OUTCOMES = [
    {
        'drug_name': 'Preladenant',
        'outcome_type': 'failure',
        'context': 'Phase II trials for Parkinson\'s disease showed limited efficacy. A2A antagonist.',
        'evidence_level': 'Clinical trial',
        'notes': 'Discontinued development'
    },
    {
        'drug_name': 'Istradefylline',
        'outcome_type': 'partial_success',
        'context': 'Approved for Parkinson\'s disease in Japan. A2A antagonist with mixed results in cancer.',
        'evidence_level': 'Approved drug',
        'notes': 'Limited cancer application data'
    },
    {
        'drug_name': 'CPI-444',
        'outcome_type': 'mixed',
        'context': 'A2A antagonist in clinical trials. Some responses observed but not consistent.',
        'evidence_level': 'Clinical trial',
        'notes': 'Ongoing development'
    },
    {
        'drug_name': 'AB928',
        'outcome_type': 'mixed',
        'context': 'Dual A2A/A2B antagonist. Early clinical data shows promise but limited patient numbers.',
        'evidence_level': 'Clinical trial',
        'notes': 'Phase I/II ongoing'
    },
    {
        'drug_name': 'CD73 inhibitors',
        'outcome_type': 'mixed',
        'context': 'Multiple CD73 inhibitors in development. Preclinical data promising, clinical data limited.',
        'evidence_level': 'Preclinical/Clinical',
        'notes': 'Various compounds in pipeline'
    },
]

# Curated drug outcomes for PD-1/PD-L1 mechanism
PD1_PDL1_DRUG_OUTCOMES = [
    {
        'drug_name': 'Pembrolizumab',
        'outcome_type': 'success',
        'context': 'Approved for multiple cancer types. Anti-PD-1 monoclonal antibody showing significant efficacy in melanoma, NSCLC, and other cancers.',
        'evidence_level': 'Approved drug',
        'notes': 'First PD-1 inhibitor approved by FDA. High response rates in selected patient populations.'
    },
    {
        'drug_name': 'Nivolumab',
        'outcome_type': 'success',
        'context': 'Approved for multiple cancer types. Anti-PD-1 monoclonal antibody with demonstrated efficacy.',
        'evidence_level': 'Approved drug',
        'notes': 'Widely used checkpoint inhibitor with proven efficacy'
    },
    {
        'drug_name': 'Atezolizumab',
        'outcome_type': 'success',
        'context': 'Approved for multiple cancer types. Anti-PD-L1 monoclonal antibody.',
        'evidence_level': 'Approved drug',
        'notes': 'PD-L1 targeting antibody'
    },
    {
        'drug_name': 'Durvalumab',
        'outcome_type': 'success',
        'context': 'Approved for NSCLC and bladder cancer. Anti-PD-L1 monoclonal antibody.',
        'evidence_level': 'Approved drug',
        'notes': 'PD-L1 inhibitor with specific indications'
    },
    {
        'drug_name': 'Avelumab',
        'outcome_type': 'partial_success',
        'context': 'Approved for Merkel cell carcinoma and bladder cancer. Anti-PD-L1 monoclonal antibody with limited indications.',
        'evidence_level': 'Approved drug',
        'notes': 'Narrower approval compared to other checkpoint inhibitors'
    },
    {
        'drug_name': 'Cemiplimab',
        'outcome_type': 'success',
        'context': 'Approved for cutaneous squamous cell carcinoma and NSCLC. Anti-PD-1 monoclonal antibody.',
        'evidence_level': 'Approved drug',
        'notes': 'More recent approval, expanding indications'
    },
]


def find_drug_by_name(drug_name: str, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find drug ID by name.
    
    Args:
        drug_name: Drug name
        conn: Database connection
        
    Returns:
        Drug ID or None
    """
    cursor = conn.cursor()
    # Try exact match first
    cursor.execute("SELECT id FROM drugs WHERE name = ? OR generic_name = ?", (drug_name, drug_name))
    result = cursor.fetchone()
    if result:
        return result[0]
    
    # Try partial match
    cursor.execute("SELECT id FROM drugs WHERE name LIKE ? OR generic_name LIKE ?", 
                   (f'%{drug_name}%', f'%{drug_name}%'))
    result = cursor.fetchone()
    return result[0] if result else None


def find_molecule_by_drug(drug_id: int, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find molecule index associated with a drug.
    
    Args:
        drug_id: Drug ID
        conn: Database connection
        
    Returns:
        Molecule index (rowid) or None
    """
    cursor = conn.cursor()
    # Get drug's PubChem CID
    cursor.execute("SELECT pubchem_cid FROM drugs WHERE id = ?", (drug_id,))
    result = cursor.fetchone()
    if result and result[0]:
        pubchem_cid = result[0]
        cursor.execute("SELECT rowid FROM molecules WHERE pubchem_cid = ?", (pubchem_cid,))
        mol_result = cursor.fetchone()
        if mol_result:
            return mol_result[0]
    
    return None


def load_drug_outcome(drug_id: Optional[int], molecule_index: Optional[int],
                      outcome_type: str, context: str, evidence_level: str,
                      notes: Optional[str] = None,
                      conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load a drug outcome into the database.
    
    Args:
        drug_id: Drug ID (optional)
        molecule_index: Molecule index (optional)
        outcome_type: Type of outcome (partial_success/failure/mixed)
        context: Context description
        evidence_level: Level of evidence
        notes: Optional notes
        conn: Optional database connection
        
    Returns:
        Outcome ID if successful, None otherwise
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Check if outcome already exists
        if drug_id:
            cursor.execute("""
                SELECT id FROM drug_outcomes 
                WHERE drug_id = ? AND outcome_type = ?
            """, (drug_id, outcome_type))
            existing = cursor.fetchone()
            if existing:
                return existing[0]
        elif molecule_index:
            cursor.execute("""
                SELECT id FROM drug_outcomes 
                WHERE molecule_index = ? AND outcome_type = ?
            """, (molecule_index, outcome_type))
            existing = cursor.fetchone()
            if existing:
                return existing[0]
        
        # Insert outcome
        cursor.execute("""
            INSERT INTO drug_outcomes (drug_id, molecule_index, outcome_type, context,
                                     evidence_level, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (drug_id, molecule_index, outcome_type, context, evidence_level, notes))
        
        outcome_id = cursor.lastrowid
        conn.commit()
        return outcome_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading drug outcome: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def load_adenosine_drug_outcomes(conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load curated drug outcomes for adenosine mechanism.
    
    Args:
        conn: Optional database connection
        
    Returns:
        Number of outcomes loaded
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        count = 0
        for outcome_data in ADENOSINE_DRUG_OUTCOMES:
            drug_name = outcome_data['drug_name']
            drug_id = find_drug_by_name(drug_name, conn)
            molecule_index = None
            
            if drug_id:
                molecule_index = find_molecule_by_drug(drug_id, conn)
            
            outcome_id = load_drug_outcome(
                drug_id=drug_id,
                molecule_index=molecule_index,
                outcome_type=outcome_data['outcome_type'],
                context=outcome_data['context'],
                evidence_level=outcome_data['evidence_level'],
                notes=outcome_data.get('notes'),
                conn=conn
            )
            
            if outcome_id:
                count += 1
        
        print(f"✅ Loaded {count} drug outcomes for adenosine mechanism")
        return count
        
    finally:
        if should_close:
            conn.close()


def load_pd1_pdl1_drug_outcomes(conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load curated drug outcomes for PD-1/PD-L1 mechanism.
    
    Args:
        conn: Optional database connection
        
    Returns:
        Number of outcomes loaded
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        count = 0
        for outcome_data in PD1_PDL1_DRUG_OUTCOMES:
            drug_name = outcome_data['drug_name']
            drug_id = find_drug_by_name(drug_name, conn)
            molecule_index = None
            
            if drug_id:
                molecule_index = find_molecule_by_drug(drug_id, conn)
            
            outcome_id = load_drug_outcome(
                drug_id=drug_id,
                molecule_index=molecule_index,
                outcome_type=outcome_data['outcome_type'],
                context=outcome_data['context'],
                evidence_level=outcome_data['evidence_level'],
                notes=outcome_data.get('notes'),
                conn=conn
            )
            
            if outcome_id:
                count += 1
        
        print(f"✅ Loaded {count} drug outcomes for PD-1/PD-L1 mechanism")
        return count
        
    finally:
        if should_close:
            conn.close()


def load_drug_outcomes_for_mechanism(mechanism_id: int, conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load drug outcomes for a mechanism (determines which curated set to use).
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        Number of outcomes loaded
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM mechanisms WHERE id = ?", (mechanism_id,))
        result = cursor.fetchone()
        
        if not result:
            print(f"⚠️  Mechanism {mechanism_id} not found")
            return 0
        
        mechanism_name = result[0]
        
        # Determine which curated outcomes to load based on mechanism name
        if 'Adenosine' in mechanism_name or 'adenosine' in mechanism_name.lower():
            return load_adenosine_drug_outcomes(conn)
        elif 'PD-1' in mechanism_name or 'PD-L1' in mechanism_name or 'PD1' in mechanism_name.upper():
            return load_pd1_pdl1_drug_outcomes(conn)
        else:
            print(f"⚠️  No curated outcomes available for mechanism: {mechanism_name}")
            return 0
        
    finally:
        if should_close:
            conn.close()


def get_drug_outcomes_for_mechanism(mechanism_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get drug outcomes for a mechanism.
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        List of outcome dictionaries
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            return []
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Get mechanism name to determine which outcomes to return
        cursor.execute("SELECT name FROM mechanisms WHERE id = ?", (mechanism_id,))
        mechanism_result = cursor.fetchone()
        if not mechanism_result:
            return []
        
        mechanism_name = mechanism_result[0]
        
        # Determine which drug outcomes belong to this mechanism based on drug names
        # This is a fallback when molecule_index/drug_id links don't exist
        mechanism_drug_names = []
        if 'Adenosine' in mechanism_name or 'adenosine' in mechanism_name.lower():
            mechanism_drug_names = [outcome['drug_name'] for outcome in ADENOSINE_DRUG_OUTCOMES]
        elif 'PD-1' in mechanism_name or 'PD-L1' in mechanism_name or 'PD1' in mechanism_name.upper():
            mechanism_drug_names = [outcome['drug_name'] for outcome in PD1_PDL1_DRUG_OUTCOMES]
        
        all_outcomes = []
        seen_ids = set()
        columns = None
        
        # First, try to get outcomes linked through ligands -> targets -> mechanisms
        cursor.execute("""
            SELECT DISTINCT do.*
            FROM drug_outcomes do
            INNER JOIN ligands l ON do.molecule_index = l.molecule_index
            INNER JOIN targets t ON l.target_id = t.id
            INNER JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ? AND do.molecule_index IS NOT NULL
        """, (mechanism_id,))
        rows1 = cursor.fetchall()
        if cursor.description:
            columns = [d[0] for d in cursor.description]
        
        for row in rows1:
            row_id = row[0]
            if row_id not in seen_ids:
                seen_ids.add(row_id)
                all_outcomes.append(dict(zip(columns, row)) if columns else {})
        
        # Also get outcomes that might be linked through drug_id -> drugs -> molecules -> ligands
        cursor.execute("""
            SELECT DISTINCT do.*
            FROM drug_outcomes do
            INNER JOIN drugs d ON do.drug_id = d.id
            INNER JOIN molecules m ON d.pubchem_cid = m.pubchem_cid
            INNER JOIN ligands l ON m.rowid = l.molecule_index
            INNER JOIN targets t ON l.target_id = t.id
            INNER JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ? AND do.molecule_index IS NULL
        """, (mechanism_id,))
        rows2 = cursor.fetchall()
        
        for row in rows2:
            row_id = row[0]
            if row_id not in seen_ids:
                seen_ids.add(row_id)
                all_outcomes.append(dict(zip(columns, row)) if columns else {})
        
        # Fallback: If no outcomes found through JOINs, try to match by drug names
        # This handles cases where outcomes exist but aren't linked to molecules/ligands
        if not all_outcomes and mechanism_drug_names:
            # Get all outcomes and try to match by context/notes containing drug names
            cursor.execute("SELECT * FROM drug_outcomes")
            all_outcome_rows = cursor.fetchall()
            outcome_columns = [d[0] for d in cursor.description] if cursor.description else []
            
            for row in all_outcome_rows:
                row_id = row[0]
                if row_id in seen_ids:
                    continue
                
                outcome_dict = dict(zip(outcome_columns, row)) if outcome_columns else {}
                context = outcome_dict.get('context', '') or ''
                notes = outcome_dict.get('notes', '') or ''
                
                # Check if any mechanism drug name appears in context or notes
                for drug_name in mechanism_drug_names:
                    if drug_name.lower() in context.lower() or drug_name.lower() in notes.lower():
                        seen_ids.add(row_id)
                        all_outcomes.append(outcome_dict)
                        break
        
        # Sort by outcome type and evidence level
        all_outcomes.sort(key=lambda x: (x.get('outcome_type', ''), x.get('evidence_level', '')))
        
        return all_outcomes
    finally:
        if should_close:
            conn.close()


def get_drug_outcomes_by_type(outcome_type: str, conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get drug outcomes by type.
    
    Args:
        outcome_type: Type of outcome (partial_success/failure/mixed)
        conn: Optional database connection
        
    Returns:
        List of outcome dictionaries
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
            SELECT * FROM drug_outcomes
            WHERE outcome_type = ?
            ORDER BY evidence_level
        """, (outcome_type,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        outcomes = [dict(zip(columns, row)) for row in rows]
        
        return outcomes
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # Test loading drug outcomes
    print("🧪 Testing drug outcome loader...")
    count = load_adenosine_drug_outcomes()
    print(f"✅ Loaded {count} drug outcomes")
