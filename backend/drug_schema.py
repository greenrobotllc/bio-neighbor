"""
Database schema for drugs table.
Handles creation and management of drugs table.
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, Optional

from data_loader import DB_PATH


def create_drugs_table(conn: sqlite3.Connection):
    """
    Create drugs table if it doesn't exist.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drugs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            generic_name TEXT,
            brand_names TEXT,
            pubchem_cid TEXT,
            drugbank_id TEXT,
            description TEXT,
            indication TEXT,
            active_ingredients TEXT,
            inactive_ingredients TEXT,
            dosage_form TEXT,
            route TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_name ON drugs(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_generic_name ON drugs(generic_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_pubchem_cid ON drugs(pubchem_cid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_drugbank_id ON drugs(drugbank_id)")
    
    conn.commit()


def update_drug_diseases_table(conn: sqlite3.Connection):
    """
    Update drug_diseases table to include drug_id column.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    # Check if drug_id column exists
    cursor.execute("PRAGMA table_info(drug_diseases)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'drug_id' not in columns:
        # Add drug_id column
        cursor.execute("""
            ALTER TABLE drug_diseases 
            ADD COLUMN drug_id INTEGER
        """)
        
        # Add foreign key constraint
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drug_diseases_drug_id 
            ON drug_diseases(drug_id)
        """)
        
        conn.commit()


def initialize_drug_schema():
    """
    Initialize drugs table schema in the database.
    """
    if not DB_PATH.exists():
        print("⚠️  Database not found. Please run data setup first.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    try:
        create_drugs_table(conn)
        update_drug_diseases_table(conn)
        print("✅ Drugs table schema initialized")
    finally:
        conn.close()


if __name__ == "__main__":
    initialize_drug_schema()

