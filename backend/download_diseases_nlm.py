"""
Bulk download diseases using NLM Clinical Tables API.
The National Library of Medicine provides a comprehensive medical conditions database
with ICD-10-CM codes, ICD-9-CM codes, and synonyms.

References:
- API: https://clinicaltables.nlm.nih.gov/apidoc/conditions/v3/doc.html
- Download: https://clinicaltables.nlm.nih.gov/ctss-downloads/cond_proc_download-2025-10-01.json.zip
"""

import argparse
import sys
import time
import requests
import json
import zipfile
from pathlib import Path
from typing import List, Optional, Dict
from io import BytesIO

from drugbank_loader import save_disease_data_to_db
from data_loader import DB_PATH
from db_migrations import migrate_database

# NLM Clinical Tables API
NLM_API_BASE = "https://clinicaltables.nlm.nih.gov/api/conditions/v3/search"
NLM_DOWNLOAD_URL = "https://clinicaltables.nlm.nih.gov/ctss-downloads/cond_proc_download-2025-10-01.json.zip"


def download_nlm_diseases_file() -> Optional[Dict]:
    """
    Download the complete NLM medical conditions dataset.
    
    Returns:
        Dictionary with disease data or None if download fails
    """
    print("📥 Downloading NLM medical conditions dataset...")
    print(f"   URL: {NLM_DOWNLOAD_URL}")
    
    try:
        response = requests.get(NLM_DOWNLOAD_URL, timeout=300, stream=True)
        response.raise_for_status()
        
        print("✅ Download complete, extracting...")
        
        # Extract ZIP file
        with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
            # Find the JSON file
            json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
            if not json_files:
                print("❌ No JSON file found in ZIP")
                return None
            
            json_file = json_files[0]
            print(f"   Extracting: {json_file}")
            
            with zip_file.open(json_file) as f:
                data = json.load(f)
            
            print(f"✅ Extracted {len(data) if isinstance(data, list) else 'data'} items")
            return data
            
    except Exception as e:
        print(f"❌ Error downloading NLM dataset: {e}")
        return None


def get_diseases_from_api(max_diseases: Optional[int] = None, search_term: str = "") -> List[Dict]:
    """
    Get diseases from NLM Clinical Tables API.
    
    Args:
        max_diseases: Maximum number of diseases to retrieve
        search_term: Optional search term (empty = all diseases)
        
    Returns:
        List of disease dictionaries
    """
    print("🔍 Fetching diseases from NLM Clinical Tables API...")
    
    diseases = []
    offset = 0
    count = 500  # Max per request
    max_total = max_diseases or 7500  # API limit is 7,500
    
    # Fields to retrieve
    ef_fields = "primary_name,consumer_name,key_id,icd10cm_codes,icd10cm,term_icd9_code,term_icd9_text,synonyms"
    df_fields = "consumer_name,primary_name"
    
    while len(diseases) < max_total:
        try:
            params = {
                'terms': search_term if search_term else '*',
                'count': min(count, max_total - len(diseases)),
                'offset': offset,
                'ef': ef_fields,
                'df': df_fields,
                'cf': 'key_id'
            }
            
            response = requests.get(NLM_API_BASE, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # API returns: [total_count, [codes], {extra_fields}, [display_fields], [code_systems]]
            if len(data) < 4:
                break
            
            total_count = data[0]
            codes = data[1]
            extra_data = data[2] if len(data) > 2 else {}
            display_fields = data[3] if len(data) > 3 else []
            
            if not codes:
                break
            
            # Process each disease
            for i, code in enumerate(codes):
                disease = {
                    'key_id': code,
                    'primary_name': extra_data.get('primary_name', [None])[i] if extra_data.get('primary_name') else None,
                    'consumer_name': extra_data.get('consumer_name', [None])[i] if extra_data.get('consumer_name') else None,
                    'icd10cm_codes': extra_data.get('icd10cm_codes', [None])[i] if extra_data.get('icd10cm_codes') else None,
                    'icd9_code': extra_data.get('term_icd9_code', [None])[i] if extra_data.get('term_icd9_code') else None,
                    'icd9_text': extra_data.get('term_icd9_text', [None])[i] if extra_data.get('term_icd9_text') else None,
                    'synonyms': extra_data.get('synonyms', [None])[i] if extra_data.get('synonyms') else None,
                }
                
                # Use consumer_name or primary_name as the main name
                disease['name'] = disease['consumer_name'] or disease['primary_name'] or f"Disease_{code}"
                
                diseases.append(disease)
            
            print(f"   Retrieved {len(diseases)}/{min(max_total, total_count)} diseases...")
            
            if len(diseases) >= total_count or len(codes) < count:
                break
            
            offset += len(codes)
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            print(f"⚠️  Error fetching from API: {e}")
            break
    
    print(f"✅ Retrieved {len(diseases)} diseases from API")
    return diseases[:max_diseases] if max_diseases else diseases


def parse_nlm_json_data(data: Dict, max_diseases: Optional[int] = None) -> List[Dict]:
    """
    Parse the downloaded NLM JSON data.
    
    Args:
        data: JSON data from NLM download
        max_diseases: Maximum number of diseases to parse
        
    Returns:
        List of disease dictionaries
    """
    print("📊 Parsing NLM disease data...")
    
    diseases = []
    
    # The JSON structure may vary, try to handle different formats
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common keys
        items = data.get('conditions', data.get('diseases', data.get('items', [])))
        if not items:
            # If it's a flat dict, try to extract values
            items = list(data.values()) if data else []
    else:
        print("❌ Unknown data format")
        return []
    
    for i, item in enumerate(items):
        if max_diseases and len(diseases) >= max_diseases:
            break
        
        if isinstance(item, dict):
            disease = {
                'key_id': item.get('key_id') or item.get('id') or str(i),
                'primary_name': item.get('primary_name') or item.get('name'),
                'consumer_name': item.get('consumer_name'),
                'icd10cm_codes': item.get('icd10cm_codes') or item.get('icd10_codes'),
                'icd9_code': item.get('term_icd9_code') or item.get('icd9_code'),
                'icd9_text': item.get('term_icd9_text') or item.get('icd9_text'),
                'synonyms': item.get('synonyms') or item.get('synonym', []),
            }
            
            disease['name'] = disease['consumer_name'] or disease['primary_name'] or f"Disease_{disease['key_id']}"
            diseases.append(disease)
        elif isinstance(item, (list, tuple)) and len(item) > 0:
            # Handle array format
            disease = {
                'key_id': str(item[0]) if len(item) > 0 else str(i),
                'name': str(item[1]) if len(item) > 1 else f"Disease_{i}",
                'primary_name': str(item[1]) if len(item) > 1 else None,
            }
            diseases.append(disease)
    
    print(f"✅ Parsed {len(diseases)} diseases")
    return diseases


def download_diseases_from_nlm(max_diseases: Optional[int] = None, use_download: bool = True) -> int:
    """
    Download diseases using NLM Clinical Tables.
    
    Args:
        max_diseases: Maximum number of diseases to download
        use_download: If True, try to download the complete dataset file first
        
    Returns:
        Number of diseases downloaded
    """
    print("=" * 60)
    print("📥 Bulk Downloading Diseases from NLM Clinical Tables")
    print("=" * 60)
    
    # Ensure database schema is up to date
    print("\n🔧 Checking database schema...")
    if not migrate_database():
        print("❌ Database migration failed")
        return 0
    print("✅ Database schema is up to date")
    
    diseases_data = []
    
    # Try to download the complete dataset first
    if use_download:
        print("\n🔍 Step 1: Attempting to download complete NLM dataset...")
        downloaded_data = download_nlm_diseases_file()
        
        if downloaded_data:
            print("✅ Using downloaded dataset")
            diseases_data = parse_nlm_json_data(downloaded_data, max_diseases)
        else:
            print("⚠️  Download failed, falling back to API...")
            use_download = False
    
    # Fallback to API if download failed or not requested
    if not diseases_data:
        print("\n🔍 Step 1: Fetching diseases from NLM API...")
        diseases_data = get_diseases_from_api(max_diseases)
    
    if not diseases_data:
        print("❌ No diseases retrieved")
        return 0
    
    # Limit to max_diseases if specified
    if max_diseases:
        diseases_data = diseases_data[:max_diseases]
    
    print(f"\n✅ Found {len(diseases_data)} diseases to save")
    print()
    
    # Step 2: Save diseases to database
    print("💾 Step 2: Saving diseases to database...")
    
    diseases_saved = 0
    
    # Group diseases for batch saving
    # The save_disease_data_to_db function expects a list of disease-drug relationships
    # For now, we'll save diseases without drugs (they can be linked later)
    
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get column list (schema should already be migrated)
        cursor.execute("PRAGMA table_info(diseases)")
        column_info = cursor.fetchall()
        available_columns = {row[1] for row in column_info}
        
        for disease in diseases_data:
            try:
                # Check if disease already exists
                cursor.execute("SELECT id FROM diseases WHERE name = ?", (disease['name'],))
                if cursor.fetchone():
                    continue  # Skip duplicates
                
                # Build INSERT statement based on available columns
                columns = ['name']
                values = [disease['name']]
                
                # Add optional columns if they exist in the table
                optional_fields = {
                    'key_id': disease.get('key_id'),
                    'primary_name': disease.get('primary_name'),
                    'consumer_name': disease.get('consumer_name'),
                    'icd10cm_codes': json.dumps(disease.get('icd10cm_codes')) if disease.get('icd10cm_codes') else None,
                    'icd9_code': disease.get('icd9_code'),
                    'icd9_text': disease.get('icd9_text'),
                    'synonyms': json.dumps(disease.get('synonyms')) if disease.get('synonyms') else None,
                }
                
                for col_name, col_value in optional_fields.items():
                    if col_name in available_columns:
                        columns.append(col_name)
                        values.append(col_value)
                
                # Also include mesh_id and description if they exist (for compatibility)
                if 'mesh_id' in available_columns:
                    columns.append('mesh_id')
                    values.append(None)
                if 'description' in available_columns:
                    columns.append('description')
                    values.append(None)
                
                # Build and execute INSERT
                placeholders = ','.join(['?'] * len(values))
                columns_str = ','.join(columns)
                cursor.execute(f"""
                    INSERT INTO diseases ({columns_str})
                    VALUES ({placeholders})
                """, values)
                
                diseases_saved += 1
                
                if diseases_saved % 100 == 0:
                    print(f"   Saved {diseases_saved}/{len(diseases_data)} diseases...")
                
            except sqlite3.IntegrityError:
                # Duplicate, skip
                continue
            except Exception as e:
                print(f"  ⚠️  Error saving disease '{disease.get('name')}': {e}")
                continue
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error saving diseases: {e}")
        import traceback
        traceback.print_exc()
        return 0
    
    print("\n" + "=" * 60)
    print(f"✅ Bulk download complete: {diseases_saved} diseases saved")
    print("=" * 60)
    
    return diseases_saved


def main():
    parser = argparse.ArgumentParser(
        description='Bulk download diseases using NLM Clinical Tables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all diseases from NLM (up to 7,500 via API)
  python download_diseases_nlm.py --max-diseases 10000
  
  # Download using the complete dataset file (recommended for large downloads)
  python download_diseases_nlm.py --max-diseases 10000 --use-download
  
  # Use API only (no file download)
  python download_diseases_nlm.py --max-diseases 1000 --no-download

References:
- API: https://clinicaltables.nlm.nih.gov/apidoc/conditions/v3/doc.html
- Download: https://clinicaltables.nlm.nih.gov/ctss-downloads/cond_proc_download-2025-10-01.json.zip
- Provides 2,400+ medical conditions with ICD-10-CM and ICD-9-CM codes
        """
    )
    
    parser.add_argument(
        '--max-diseases',
        type=int,
        default=None,
        help='Maximum number of diseases to download (default: None = all available)'
    )
    
    parser.add_argument(
        '--use-download',
        action='store_true',
        default=True,
        help='Try to download the complete dataset file first (default: True)'
    )
    
    parser.add_argument(
        '--no-download',
        dest='use_download',
        action='store_false',
        help='Use API only, do not download the dataset file'
    )
    
    args = parser.parse_args()
    
    # Check if molecule database exists
    if not DB_PATH.exists():
        print("❌ Error: Molecules database not found.")
        print("   Please run 'python backend/main.py setup' first to create the database.")
        sys.exit(1)
    
    try:
        count = download_diseases_from_nlm(
            max_diseases=args.max_diseases,
            use_download=args.use_download
        )
        sys.exit(0 if count > 0 else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Download interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error during bulk download: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

