"""
Cancer mapping loader for cancer mechanism research.
Maps mechanisms to cancer types using Reactome and other sources.
"""

import sqlite3
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
from data_loader import DB_PATH

# Reactome API base URL
REACTOME_API_BASE = "https://reactome.org/ContentService"

# Curated cancer-mechanism mappings for adenosine
# In production, this would be expanded with Reactome pathway data and literature
ADENOSINE_CANCER_MAPPINGS = [
    {
        'cancer_type': 'Melanoma',
        'activity_level': 'High',
        'evidence_source': 'Literature - High CD73 expression in melanoma, A2A blockade shows efficacy'
    },
    {
        'cancer_type': 'Non-small cell lung cancer',
        'activity_level': 'High',
        'evidence_source': 'Literature - Adenosine pathway active, multiple clinical trials'
    },
    {
        'cancer_type': 'Renal cell carcinoma',
        'activity_level': 'High',
        'evidence_source': 'Literature - CD73 overexpression, immune suppression mechanism'
    },
    {
        'cancer_type': 'Colorectal cancer',
        'activity_level': 'Moderate',
        'evidence_source': 'Literature - CD39/CD73 expression, variable activity'
    },
    {
        'cancer_type': 'Breast cancer',
        'activity_level': 'Moderate',
        'evidence_source': 'Literature - Adenosine signaling present, context-dependent'
    },
    {
        'cancer_type': 'Pancreatic cancer',
        'activity_level': 'High',
        'evidence_source': 'Literature - Strong adenosine-mediated immune suppression'
    },
]

# Curated cancer-mechanism mappings for PD-1/PD-L1
PD1_PDL1_CANCER_MAPPINGS = [
    {
        'cancer_type': 'Melanoma',
        'activity_level': 'High',
        'evidence_source': 'Clinical - PD-1/PD-L1 inhibitors approved, high response rates'
    },
    {
        'cancer_type': 'Non-small cell lung cancer',
        'activity_level': 'High',
        'evidence_source': 'Clinical - Multiple approved checkpoint inhibitors, standard of care'
    },
    {
        'cancer_type': 'Renal cell carcinoma',
        'activity_level': 'High',
        'evidence_source': 'Clinical - Checkpoint inhibitors show significant efficacy'
    },
    {
        'cancer_type': 'Hodgkin lymphoma',
        'activity_level': 'High',
        'evidence_source': 'Clinical - High response rates to PD-1 blockade'
    },
    {
        'cancer_type': 'Head and neck squamous cell carcinoma',
        'activity_level': 'High',
        'evidence_source': 'Clinical - PD-1 inhibitors approved, especially in PD-L1 positive tumors'
    },
    {
        'cancer_type': 'Urothelial carcinoma',
        'activity_level': 'High',
        'evidence_source': 'Clinical - Checkpoint inhibitors approved for advanced disease'
    },
    {
        'cancer_type': 'Gastric cancer',
        'activity_level': 'Moderate',
        'evidence_source': 'Clinical - PD-1 inhibitors show benefit in selected patients'
    },
    {
        'cancer_type': 'Hepatocellular carcinoma',
        'activity_level': 'Moderate',
        'evidence_source': 'Clinical - PD-1/PD-L1 inhibitors approved, variable responses'
    },
]


def fetch_reactome_pathways_for_target(uniprot_id: str) -> List[str]:
    """
    Fetch Reactome pathways for a target protein.
    
    Args:
        uniprot_id: UniProt accession ID
        
    Returns:
        List of pathway names
    """
    try:
        url = f"{REACTOME_API_BASE}/query/enhanced/participants/{uniprot_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        pathways = []
        if isinstance(data, list):
            for item in data:
                if 'pathways' in item:
                    for pathway in item['pathways']:
                        if 'displayName' in pathway:
                            pathways.append(pathway['displayName'])
        
        return list(set(pathways))  # Remove duplicates
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error fetching Reactome pathways for {uniprot_id}: {e}")
        return []
    except Exception as e:
        print(f"⚠️  Error parsing Reactome data for {uniprot_id}: {e}")
        return []


def load_cancer_mechanism_mapping(mechanism_id: int, cancer_type: str,
                                  activity_level: str, evidence_source: str,
                                  conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Load a cancer-mechanism mapping.
    
    Args:
        mechanism_id: Mechanism ID
        cancer_type: Cancer type name
        activity_level: Activity level (High/Moderate/Low)
        evidence_source: Source of evidence
        conn: Optional database connection
        
    Returns:
        Mapping ID if successful, None otherwise
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        # Check if mapping already exists
        cursor.execute("""
            SELECT id FROM cancer_mechanisms 
            WHERE mechanism_id = ? AND cancer_type = ?
        """, (mechanism_id, cancer_type))
        existing = cursor.fetchone()
        if existing:
            return existing[0]
        
        # Insert mapping
        cursor.execute("""
            INSERT INTO cancer_mechanisms (cancer_type, mechanism_id, activity_level, evidence_source)
            VALUES (?, ?, ?, ?)
        """, (cancer_type, mechanism_id, activity_level, evidence_source))
        
        mapping_id = cursor.lastrowid
        conn.commit()
        return mapping_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error loading cancer-mechanism mapping: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if should_close:
            conn.close()


def load_pd1_pdl1_cancer_mappings(mechanism_id: int,
                                  conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load curated cancer mappings for PD-1/PD-L1 mechanism.
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        Number of mappings loaded
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        count = 0
        for mapping_data in PD1_PDL1_CANCER_MAPPINGS:
            mapping_id = load_cancer_mechanism_mapping(
                mechanism_id=mechanism_id,
                cancer_type=mapping_data['cancer_type'],
                activity_level=mapping_data['activity_level'],
                evidence_source=mapping_data['evidence_source'],
                conn=conn
            )
            if mapping_id:
                count += 1
        
        print(f"✅ Loaded {count} cancer-mechanism mappings for PD-1/PD-L1 mechanism {mechanism_id}")
        return count
        
    finally:
        if should_close:
            conn.close()


def load_adenosine_cancer_mappings(mechanism_id: int,
                                   conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Load curated cancer mappings for adenosine mechanism.
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        Number of mappings loaded
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        count = 0
        for mapping_data in ADENOSINE_CANCER_MAPPINGS:
            mapping_id = load_cancer_mechanism_mapping(
                mechanism_id=mechanism_id,
                cancer_type=mapping_data['cancer_type'],
                activity_level=mapping_data['activity_level'],
                evidence_source=mapping_data['evidence_source'],
                conn=conn
            )
            if mapping_id:
                count += 1
        
        print(f"✅ Loaded {count} cancer-mechanism mappings for mechanism {mechanism_id}")
        return count
        
    finally:
        if should_close:
            conn.close()


def get_cancers_for_mechanism(mechanism_id: int,
                              conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all cancers associated with a mechanism.
    
    Args:
        mechanism_id: Mechanism ID
        conn: Optional database connection
        
    Returns:
        List of cancer-mechanism mapping dictionaries
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
            SELECT * FROM cancer_mechanisms
            WHERE mechanism_id = ?
            ORDER BY 
                CASE activity_level
                    WHEN 'High' THEN 1
                    WHEN 'Moderate' THEN 2
                    WHEN 'Low' THEN 3
                    ELSE 4
                END,
                cancer_type
        """, (mechanism_id,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        mappings = [dict(zip(columns, row)) for row in rows]
        
        return mappings
    finally:
        if should_close:
            conn.close()


def get_mechanisms_for_cancer(cancer_type: str,
                              conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Get all mechanisms associated with a cancer type.
    
    Args:
        cancer_type: Cancer type name
        conn: Optional database connection
        
    Returns:
        List of cancer-mechanism mapping dictionaries
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
            SELECT cm.*, m.name as mechanism_name
            FROM cancer_mechanisms cm
            JOIN mechanisms m ON cm.mechanism_id = m.id
            WHERE cm.cancer_type = ?
            ORDER BY 
                CASE cm.activity_level
                    WHEN 'High' THEN 1
                    WHEN 'Moderate' THEN 2
                    WHEN 'Low' THEN 3
                    ELSE 4
                END
        """, (cancer_type,))
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        mappings = [dict(zip(columns, row)) for row in rows]
        
        return mappings
    finally:
        if should_close:
            conn.close()


def get_all_cancer_types(conn: Optional[sqlite3.Connection] = None) -> List[str]:
    """
    Get all unique cancer types in the database.
    
    Args:
        conn: Optional database connection
        
    Returns:
        List of cancer type names
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
            SELECT DISTINCT cancer_type 
            FROM cancer_mechanisms
            ORDER BY cancer_type
        """)
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # Test loading cancer mappings
    print("🧪 Testing cancer mapping loader...")
    print("✅ Cancer mapping loader module ready")
