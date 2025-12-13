"""
Database schema definitions for bio-neighbor.
Defines all tables and their structure.
"""

from typing import Dict, List, Tuple

# Schema version - increment when making schema changes
SCHEMA_VERSION = 3

# Table definitions
# Format: table_name -> (columns, indexes, foreign_keys)
SCHEMA: Dict[str, Dict] = {
    'molecules': {
        'columns': [
            ('rowid', 'INTEGER PRIMARY KEY'),
            ('smiles', 'TEXT NOT NULL'),
            ('name', 'TEXT'),
            ('molecular_weight', 'REAL'),
            ('pubchem_cid', 'TEXT'),
            ('chembl_id', 'TEXT'),
            ('zinc_id', 'TEXT'),
            ('is_approved', 'INTEGER DEFAULT 0'),
            ('targets', 'TEXT'),
            ('fingerprint', 'BLOB'),
            ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
        ],
        'indexes': [
            'CREATE INDEX IF NOT EXISTS idx_molecules_smiles ON molecules(smiles)',
            'CREATE INDEX IF NOT EXISTS idx_molecules_name ON molecules(name)',
            'CREATE INDEX IF NOT EXISTS idx_molecules_pubchem_cid ON molecules(pubchem_cid)',
            'CREATE INDEX IF NOT EXISTS idx_molecules_chembl_id ON molecules(chembl_id)',
        ],
        'foreign_keys': []
    },
    
    'diseases': {
        'columns': [
            ('id', 'INTEGER PRIMARY KEY AUTOINCREMENT'),
            ('name', 'TEXT NOT NULL UNIQUE'),
            ('mesh_id', 'TEXT'),
            ('description', 'TEXT'),
            ('key_id', 'TEXT'),
            ('primary_name', 'TEXT'),
            ('consumer_name', 'TEXT'),
            ('icd10cm_codes', 'TEXT'),
            ('icd9_code', 'TEXT'),
            ('icd9_text', 'TEXT'),
            ('synonyms', 'TEXT'),
            ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
        ],
        'indexes': [
            'CREATE INDEX IF NOT EXISTS idx_disease_name ON diseases(name)',
            'CREATE INDEX IF NOT EXISTS idx_disease_key_id ON diseases(key_id)',
        ],
        'foreign_keys': []
    },
    
    'drugs': {
        'columns': [
            ('id', 'INTEGER PRIMARY KEY AUTOINCREMENT'),
            ('name', 'TEXT NOT NULL'),
            ('generic_name', 'TEXT'),
            ('brand_names', 'TEXT'),
            ('pubchem_cid', 'TEXT'),
            ('drugbank_id', 'TEXT'),
            ('description', 'TEXT'),
            ('indication', 'TEXT'),
            ('active_ingredients', 'TEXT'),
            ('inactive_ingredients', 'TEXT'),
            ('dosage_form', 'TEXT'),
            ('route', 'TEXT'),
            ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
        ],
        'indexes': [
            'CREATE INDEX IF NOT EXISTS idx_drug_name ON drugs(name)',
            'CREATE INDEX IF NOT EXISTS idx_drug_generic_name ON drugs(generic_name)',
            'CREATE INDEX IF NOT EXISTS idx_drug_pubchem_cid ON drugs(pubchem_cid)',
            'CREATE INDEX IF NOT EXISTS idx_drug_drugbank_id ON drugs(drugbank_id)',
        ],
        'foreign_keys': []
    },
    
    'drug_diseases': {
        'columns': [
            ('id', 'INTEGER PRIMARY KEY AUTOINCREMENT'),
            ('molecule_index', 'INTEGER'),  # Nullable - drug may not have matched molecule yet
            ('disease_id', 'INTEGER NOT NULL'),
            ('drug_id', 'INTEGER'),  # Nullable - may link via drug_id instead
            ('indication_type', 'TEXT'),
            ('evidence_level', 'TEXT'),
        ],
        'indexes': [
            'CREATE INDEX IF NOT EXISTS idx_drug_disease_molecule ON drug_diseases(molecule_index)',
            'CREATE INDEX IF NOT EXISTS idx_drug_disease_disease ON drug_diseases(disease_id)',
        ],
        'foreign_keys': [
            'FOREIGN KEY (disease_id) REFERENCES diseases(id)',
            'FOREIGN KEY (molecule_index) REFERENCES molecules(rowid)',
            'FOREIGN KEY (drug_id) REFERENCES drugs(id)',
        ]
    },
    
    'schema_version': {
        'columns': [
            ('version', 'INTEGER PRIMARY KEY'),
            ('applied_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
        ],
        'indexes': [],
        'foreign_keys': []
    }
}


def get_create_table_sql(table_name: str) -> str:
    """
    Get CREATE TABLE SQL for a table.
    
    Args:
        table_name: Name of the table
        
    Returns:
        SQL CREATE TABLE statement
    """
    if table_name not in SCHEMA:
        raise ValueError(f"Unknown table: {table_name}")
    
    table_def = SCHEMA[table_name]
    columns = table_def['columns']
    foreign_keys = table_def.get('foreign_keys', [])
    
    # Build column definitions
    column_defs = [f"{name} {defn}" for name, defn in columns]
    
    # Add foreign keys if any
    if foreign_keys:
        column_defs.extend(foreign_keys)
    
    columns_sql = ',\n            '.join(column_defs)
    
    return f"""CREATE TABLE IF NOT EXISTS {table_name} (
            {columns_sql}
        )"""


def get_create_index_sql(table_name: str) -> List[str]:
    """
    Get CREATE INDEX SQL statements for a table.
    
    Args:
        table_name: Name of the table
        
    Returns:
        List of SQL CREATE INDEX statements
    """
    if table_name not in SCHEMA:
        raise ValueError(f"Unknown table: {table_name}")
    
    return SCHEMA[table_name].get('indexes', [])


def get_all_tables() -> List[str]:
    """Get list of all table names."""
    return list(SCHEMA.keys())


def get_schema_version() -> int:
    """Get current schema version."""
    return SCHEMA_VERSION

