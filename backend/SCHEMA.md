# Database Schema Documentation

This document describes the database schema for bio-neighbor.

## Schema Management

The database schema is managed through:
- **`db_schema.py`**: Defines all table structures
- **`db_migrations.py`**: Handles schema migrations and versioning

## Schema Version

Current schema version: **2**

## Tables

### molecules
Primary table for storing molecular data.

| Column | Type | Description |
|--------|------|-------------|
| rowid | INTEGER PRIMARY KEY | Auto-incrementing primary key |
| smiles | TEXT NOT NULL | SMILES string representation |
| name | TEXT | Molecule name |
| molecular_weight | REAL | Molecular weight |
| pubchem_cid | TEXT | PubChem Compound ID |
| chembl_id | TEXT | ChEMBL ID |
| zinc_id | TEXT | ZINC ID |
| is_approved | INTEGER | Whether molecule is FDA approved (0/1) |
| targets | TEXT | JSON array of target proteins |
| fingerprint | BLOB | Binary fingerprint for similarity search |
| created_at | TIMESTAMP | Creation timestamp |

**Indexes:**
- `idx_molecules_smiles` on `smiles`
- `idx_molecules_name` on `name`
- `idx_molecules_pubchem_cid` on `pubchem_cid`
- `idx_molecules_chembl_id` on `chembl_id`

### diseases
Medical conditions and diseases.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-incrementing primary key |
| name | TEXT NOT NULL UNIQUE | Disease name (unique) |
| mesh_id | TEXT | MeSH ID |
| description | TEXT | Disease description |
| key_id | TEXT | NLM Clinical Tables key ID |
| primary_name | TEXT | Primary disease name |
| consumer_name | TEXT | Consumer-friendly name |
| icd10cm_codes | TEXT | JSON array of ICD-10-CM codes |
| icd9_code | TEXT | ICD-9-CM code |
| icd9_text | TEXT | ICD-9-CM text |
| synonyms | TEXT | JSON array of synonyms |
| created_at | TIMESTAMP | Creation timestamp |

**Indexes:**
- `idx_disease_name` on `name`
- `idx_disease_key_id` on `key_id`

### drugs
Drug information and details.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-incrementing primary key |
| name | TEXT NOT NULL | Drug name |
| generic_name | TEXT | Generic name |
| brand_names | TEXT | JSON array of brand names |
| pubchem_cid | TEXT | PubChem Compound ID |
| drugbank_id | TEXT | DrugBank ID |
| description | TEXT | Drug description |
| indication | TEXT | Indication/use |
| active_ingredients | TEXT | JSON array of active ingredients |
| inactive_ingredients | TEXT | JSON array of inactive ingredients |
| dosage_form | TEXT | Dosage form |
| route | TEXT | Administration route |
| created_at | TIMESTAMP | Creation timestamp |

**Indexes:**
- `idx_drug_name` on `name`
- `idx_drug_generic_name` on `generic_name`
- `idx_drug_pubchem_cid` on `pubchem_cid`
- `idx_drug_drugbank_id` on `drugbank_id`

### drug_diseases
Junction table linking drugs/molecules to diseases.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-incrementing primary key |
| molecule_index | INTEGER NOT NULL | Foreign key to molecules(rowid) |
| disease_id | INTEGER NOT NULL | Foreign key to diseases(id) |
| indication_type | TEXT | Type of indication (e.g., "approved") |
| evidence_level | TEXT | Evidence level |

**Indexes:**
- `idx_drug_disease_molecule` on `molecule_index`
- `idx_drug_disease_disease` on `disease_id`

**Foreign Keys:**
- `disease_id` → `diseases(id)`
- `molecule_index` → `molecules(rowid)`

### schema_version
Tracks database schema version for migrations.

| Column | Type | Description |
|--------|------|-------------|
| version | INTEGER PRIMARY KEY | Schema version number |
| applied_at | TIMESTAMP | When version was applied |

## Migrations

### Version 1
Initial schema with molecules, diseases, drugs, and drug_diseases tables.

### Version 2
Added NLM Clinical Tables fields to diseases table:
- `key_id`
- `primary_name`
- `consumer_name`
- `icd10cm_codes`
- `icd9_code`
- `icd9_text`
- `synonyms`

## Usage

### Running Migrations

```bash
# Check current schema version
python backend/db_migrations.py --check

# Run migrations (automatic)
python backend/db_migrations.py

# Force recreate all tables (DANGEROUS - deletes all data!)
python backend/db_migrations.py --force-recreate
```

### In Code

```python
from db_migrations import migrate_database

# Ensure schema is up to date
migrate_database()
```

## Adding New Migrations

1. Increment `SCHEMA_VERSION` in `db_schema.py`
2. Add migration definition to `MIGRATIONS` in `db_migrations.py`:
   ```python
   NEW_VERSION: (
       "Description of changes",
       [
           "ALTER TABLE table_name ADD COLUMN new_column TEXT",
           # ... more SQL statements
       ],
       None  # Optional rollback SQL
   )
   ```
3. Update table definition in `SCHEMA` in `db_schema.py` if needed

