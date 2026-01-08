"""
Database migration system for bio-neighbor.
Handles schema updates and migrations.
"""

import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import json

from data_loader import DB_PATH
from db_schema import SCHEMA_VERSION, get_create_table_sql, get_create_index_sql, get_all_tables


# Migration definitions
# Format: version -> (description, migration_sql, rollback_sql)
MIGRATIONS: Dict[int, Tuple[str, List[str], Optional[List[str]]]] = {
    1: (
        "Initial schema with molecules, diseases, drugs, and drug_diseases",
        [
            # This migration is handled by initial schema creation
        ],
        None
    ),
    2: (
        "Add NLM fields to diseases table (key_id, primary_name, consumer_name, icd10cm_codes, icd9_code, icd9_text, synonyms)",
        [
            "ALTER TABLE diseases ADD COLUMN key_id TEXT",
            "ALTER TABLE diseases ADD COLUMN primary_name TEXT",
            "ALTER TABLE diseases ADD COLUMN consumer_name TEXT",
            "ALTER TABLE diseases ADD COLUMN icd10cm_codes TEXT",
            "ALTER TABLE diseases ADD COLUMN icd9_code TEXT",
            "ALTER TABLE diseases ADD COLUMN icd9_text TEXT",
            "ALTER TABLE diseases ADD COLUMN synonyms TEXT",
        ],
        None  # No rollback for ALTER TABLE ADD COLUMN in SQLite
    ),
    3: (
        "Make molecule_index nullable in drug_diseases and ensure drug_id column exists",
        [
            # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
            # This will be handled via python-level table rebuild in apply_migration()
        ],
        None
    ),
    4: (
        "Add cancer mechanism research workspace tables (mechanisms, targets, ligands, assays, drug_outcomes, cancer_mechanisms, workspaces)",
        [
            # All new tables will be created via initialize_schema() using get_create_table_sql()
            # This migration is handled by schema initialization
        ],
        None
    ),
    5: (
        "Add unique constraint to mechanism_targets table and remove duplicate entries",
        [
            # Remove duplicate mechanism_targets entries (keep first occurrence)
            """
            DELETE FROM mechanism_targets
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM mechanism_targets
                GROUP BY mechanism_id, target_id
            )
            """,
            # Add unique index to prevent future duplicates
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mechanism_targets_unique ON mechanism_targets(mechanism_id, target_id)",
        ],
        None  # No rollback - removing duplicates is safe
    ),
}


def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """
    Get the current schema version from the database.
    
    Args:
        conn: Database connection
        
    Returns:
        Current schema version, or 0 if not set
    """
    cursor = conn.cursor()
    
    # Check if schema_version table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='schema_version'
    """)
    
    if not cursor.fetchone():
        return 0
    
    # Get latest version
    cursor.execute("SELECT MAX(version) FROM schema_version")
    result = cursor.fetchone()
    return result[0] if result and result[0] else 0


def set_schema_version(conn: sqlite3.Connection, version: int):
    """
    Set the schema version in the database.
    
    Args:
        conn: Database connection
        version: Schema version to set
    """
    cursor = conn.cursor()
    
    # Ensure schema_version table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert version
    cursor.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def _rebuild_table_from_schema(conn: sqlite3.Connection, table_name: str) -> None:
    """
    Rebuild a table from the current schema definition.
    This is used when SQLite's ALTER TABLE limitations prevent schema changes.
    
    Args:
        conn: Database connection
        table_name: Name of the table to rebuild
    """
    cursor = conn.cursor()
    tmp = f"{table_name}__old"
    savepoint_name = f"rebuild_{table_name}"
    
    # Use savepoint for atomic operation
    cursor.execute(f"SAVEPOINT {savepoint_name}")
    try:
        # Rename old table
        cursor.execute(f"ALTER TABLE {table_name} RENAME TO {tmp}")
        
        # Create new table from schema
        cursor.execute(get_create_table_sql(table_name))
        
        # Get intersecting columns (excluding id which may be auto-increment)
        cursor.execute(f"PRAGMA table_info({tmp})")
        old_cols = {r[1] for r in cursor.fetchall()}
        cursor.execute(f"PRAGMA table_info({table_name})")
        new_cols = {r[1] for r in cursor.fetchall()}
        
        # Find common columns (excluding id if it's auto-increment)
        cols = [c for c in old_cols & new_cols if c != "id"]
        
        if cols:
            cols_sql = ", ".join(cols)
            cursor.execute(
                f"INSERT INTO {table_name} ({cols_sql}) SELECT {cols_sql} FROM {tmp}"
            )
        
        # Drop old table
        cursor.execute(f"DROP TABLE {tmp}")
        
        # Release savepoint on success
        cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    except Exception:
        # Rollback to savepoint on error
        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        raise


def apply_migration(conn: sqlite3.Connection, from_version: int, to_version: int) -> bool:
    """
    Apply migrations from one version to another.
    
    Args:
        conn: Database connection
        from_version: Starting version
        to_version: Target version
        
    Returns:
        True if successful, False otherwise
    """
    if from_version >= to_version:
        return True
    
    cursor = conn.cursor()
    
    try:
        for version in range(from_version + 1, to_version + 1):
            if version not in MIGRATIONS:
                raise ValueError(f"Migration version {version} is required but not defined in MIGRATIONS. Cannot proceed.")
            
            description, migration_sql, _ = MIGRATIONS[version]
            print(f"📦 Applying migration {version}: {description}")
            
            # Special handling for migration 3: rebuild table to make molecule_index nullable
            if version == 3:
                _rebuild_table_from_schema(conn, "drug_diseases")
                # Recreate indexes dropped by the rebuild
                for index_sql in get_create_index_sql("drug_diseases"):
                    try:
                        cursor.execute(index_sql)
                    except sqlite3.OperationalError:
                        pass  # Index may already exist
                conn.commit()
                set_schema_version(conn, version)
                print(f"   ✅ Migration {version} applied successfully")
                continue
            
            # Special handling for migration 4: create new cancer research tables
            if version == 4:
                new_tables = ['mechanisms', 'targets', 'mechanism_targets', 'ligands', 
                             'assays', 'drug_outcomes', 'cancer_mechanisms', 'workspaces']
                for table_name in new_tables:
                    try:
                        # Create table
                        create_sql = get_create_table_sql(table_name)
                        cursor.execute(create_sql)
                        # Create indexes
                        for index_sql in get_create_index_sql(table_name):
                            try:
                                cursor.execute(index_sql)
                            except sqlite3.OperationalError:
                                pass  # Index may already exist
                    except sqlite3.OperationalError as e:
                        error_msg = str(e).lower()
                        if 'already exists' in error_msg:
                            print(f"   ⚠️  Table {table_name} already exists, skipping")
                        else:
                            raise
                conn.commit()
                set_schema_version(conn, version)
                print(f"   ✅ Migration {version} applied successfully")
                continue
            
            for sql in migration_sql:
                if sql.strip():  # Skip empty statements
                    try:
                        cursor.execute(sql)
                    except sqlite3.OperationalError as e:
                        # Some operations might fail if already applied (e.g., column exists)
                        error_msg = str(e).lower()
                        if 'duplicate column' in error_msg or 'already exists' in error_msg:
                            print(f"   ⚠️  Skipping (already applied): {sql[:50]}...")
                        else:
                            raise
            
            # Make migration atomic: set version before committing
            # (set_schema_version commits internally, so we don't commit here)
            set_schema_version(conn, version)
            print(f"   ✅ Migration {version} applied successfully")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error applying migration: {e}")
        import traceback
        traceback.print_exc()
        return False


def initialize_schema(conn: sqlite3.Connection, force_recreate: bool = False) -> bool:
    """
    Initialize database schema.
    
    Args:
        conn: Database connection
        force_recreate: If True, drop and recreate all tables (DANGEROUS - loses data!)
        
    Returns:
        True if successful, False otherwise
    """
    cursor = conn.cursor()
    
    try:
        if force_recreate:
            print("⚠️  WARNING: Force recreating all tables - this will DELETE ALL DATA!")
            cursor.execute("DROP TABLE IF EXISTS schema_version")
            for table_name in get_all_tables():
                if table_name != 'schema_version':
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.commit()
        
        # Create schema_version table first
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create all tables first (excluding schema_version which is already created)
        for table_name in get_all_tables():
            if table_name == 'schema_version':
                continue  # Skip schema_version, already created
            create_sql = get_create_table_sql(table_name)
            cursor.execute(create_sql)
        
        # Commit tables before creating indexes
        conn.commit()
        
        # Create indexes after all tables are created and committed
        for table_name in get_all_tables():
            if table_name == 'schema_version':
                continue
            for index_sql in get_create_index_sql(table_name):
                try:
                    cursor.execute(index_sql)
                except sqlite3.OperationalError as e:
                    # Index might already exist or column might not exist yet
                    error_msg = str(e).lower()
                    if 'already exists' in error_msg or 'duplicate' in error_msg:
                        pass  # Index already exists, skip
                    elif 'no such column' in error_msg:
                        # Column doesn't exist - this shouldn't happen with proper schema
                        # but we'll skip it and let migrations handle it
                        print(f"   ⚠️  Warning: Column missing for index: {index_sql[:50]}... ({e})")
                    else:
                        print(f"   ⚠️  Warning: Could not create index: {index_sql[:50]}... ({e})")
        
        # Set schema version
        set_schema_version(conn, SCHEMA_VERSION)
        conn.commit()
        
        print(f"✅ Schema initialized (version {SCHEMA_VERSION})")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error initializing schema: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_database(conn: Optional[sqlite3.Connection] = None, force_recreate: bool = False) -> bool:
    """
    Migrate database to latest schema version.
    
    Args:
        conn: Optional database connection (creates new if None)
        force_recreate: If True, drop and recreate all tables (DANGEROUS!)
        
    Returns:
        True if successful, False otherwise
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            # Create database file
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    try:
        if force_recreate:
            print("⚠️  Force recreate requested; reinitializing schema from scratch...")
            return initialize_schema(conn, force_recreate=True)
        
        # Get current version
        current_version = get_current_schema_version(conn)
        target_version = SCHEMA_VERSION
        
        print(f"📊 Current schema version: {current_version}")
        print(f"📊 Target schema version: {target_version}")
        
        if current_version == 0:
            # No schema version table - initialize from scratch
            print("🆕 Initializing new database schema...")
            return initialize_schema(conn, force_recreate)
        elif current_version < target_version:
            # Need to migrate
            print(f"🔄 Migrating from version {current_version} to {target_version}...")
            return apply_migration(conn, current_version, target_version)
        elif current_version > target_version:
            print(f"⚠️  Database version ({current_version}) is newer than code version ({target_version})")
            print("   This may cause compatibility issues!")
            return False
        else:
            print("✅ Database is up to date")
            return True
            
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # CLI for running migrations
    import argparse
    
    parser = argparse.ArgumentParser(description='Database migration tool')
    parser.add_argument('--force-recreate', action='store_true',
                       help='Force recreate all tables (DANGEROUS - deletes all data!)')
    parser.add_argument('--check', action='store_true',
                       help='Check current schema version and exit')
    
    args = parser.parse_args()
    
    if args.check:
        conn = sqlite3.connect(DB_PATH)
        version = get_current_schema_version(conn)
        print(f"Current schema version: {version}")
        print(f"Code schema version: {SCHEMA_VERSION}")
        conn.close()
    else:
        success = migrate_database(force_recreate=args.force_recreate)
        exit(0 if success else 1)

