"""
ETL Orchestrator for Cancer Research Data Pipeline.
Coordinates loading of all data types (targets, ligands, assays, outcomes, mappings)
for cancer research mechanisms from external APIs.
"""

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from data_loader import DB_PATH


def load_mechanism_data(mechanism_id: int, force_refresh: bool = False,
                       conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Main ETL orchestrator - loads all data types for a mechanism.
    
    Args:
        mechanism_id: Mechanism ID to load data for
        force_refresh: If True, reload even if data exists
        conn: Optional database connection
        
    Returns:
        Dictionary with counts of loaded entities and any errors/warnings
    """
    should_close = False
    if conn is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    
    result = {
        'mechanism_id': mechanism_id,
        'targets_loaded': 0,
        'ligands_loaded': 0,
        'assays_loaded': 0,
        'outcomes_loaded': 0,
        'cancer_mappings_loaded': 0,
        'errors': [],
        'warnings': [],
        'progress': []
    }
    
    try:
        print(f"\n🔄 Starting ETL for mechanism {mechanism_id}...")
        result['progress'].append("Starting ETL pipeline...")
        
        # Step 1: Load targets
        print("\n📋 Step 1: Loading targets...")
        result['progress'].append("Step 1/5: Loading targets from UniProt/IUPHAR...")
        try:
            from target_loader import load_all_targets_for_mechanism
            result['targets_loaded'] = retry_api_call(
                load_all_targets_for_mechanism,
                max_retries=2,
                delay=1.0,
                mechanism_id=mechanism_id,
                force_refresh=force_refresh,
                conn=conn
            ) or 0
            if result['targets_loaded'] > 0:
                print(f"✅ Loaded {result['targets_loaded']} targets")
                result['progress'].append(f"Step 1/5: ✅ Loaded {result['targets_loaded']} targets")
            else:
                result['warnings'].append("No new targets loaded (may already exist)")
                result['progress'].append("Step 1/5: ⚠️  No new targets (may already exist)")
        except Exception as e:
            error_msg = f"Error loading targets: {str(e)}"
            result['errors'].append(error_msg)
            result['warnings'].append("Continuing with existing target data...")
            print(f"⚠️  {error_msg}")
            import traceback
            traceback.print_exc()
        
        # Step 2: Load ligands
        print("\n🧪 Step 2: Loading ligands...")
        result['progress'].append("Step 2/5: Loading ligands from ChEMBL/PubChem...")
        try:
            from ligand_loader import load_ligands_for_mechanism_targets, get_ligands_for_mechanism
            # Check existing count before loading
            existing_ligands = get_ligands_for_mechanism(mechanism_id, conn)
            existing_count = len(existing_ligands)
            print(f"   📊 Existing ligands in database: {existing_count}")
            
            ligands_result = retry_api_call(
                load_ligands_for_mechanism_targets,
                max_retries=2,
                delay=2.0,  # Longer delay for ChEMBL API
                mechanism_id=mechanism_id,
                force_refresh=force_refresh,
                conn=conn
            )
            
            # Check count after loading
            updated_ligands = get_ligands_for_mechanism(mechanism_id, conn)
            updated_count = len(updated_ligands)
            result['ligands_loaded'] = ligands_result or 0
            
            if updated_count > existing_count:
                newly_loaded = updated_count - existing_count
                print(f"✅ Loaded {newly_loaded} new ligands (total: {updated_count})")
                result['progress'].append(f"Step 2/5: ✅ Loaded {newly_loaded} new ligands (total: {updated_count})")
                result['ligands_loaded'] = newly_loaded
            elif updated_count > 0:
                print(f"⚠️  Ligands already exist: {updated_count} total ligands found")
                result['warnings'].append(f"Ligands already exist: {updated_count} total (no new data loaded)")
                result['progress'].append(f"Step 2/5: ⚠️  {updated_count} ligands exist (no new data)")
                result['ligands_loaded'] = 0
            else:
                print(f"❌ No ligands found after loading attempt")
                print(f"   🔄 Trying curated ligand lists as fallback...")
                try:
                    from curated_ligand_loader import load_curated_ligands_for_mechanism
                    curated_loaded = load_curated_ligands_for_mechanism(mechanism_id, conn)
                    if curated_loaded > 0:
                        updated_ligands = get_ligands_for_mechanism(mechanism_id, conn)
                        updated_count = len(updated_ligands)
                        print(f"✅ Loaded {curated_loaded} curated ligands (total: {updated_count})")
                        result['progress'].append(f"Step 2/5: ✅ Loaded {curated_loaded} curated ligands (total: {updated_count})")
                        result['ligands_loaded'] = curated_loaded
                    else:
                        warning_msg = "No ligands loaded - APIs unavailable and no curated ligands found. Check /cancer-research/health/data-sources for API status."
                        result['warnings'].append(warning_msg)
                        result['progress'].append("Step 2/5: ❌ No ligands found (APIs unavailable, no curated data)")
                        result['ligands_loaded'] = 0
                except Exception as e:
                    print(f"   ⚠️  Error loading curated ligands: {e}")
                    warning_msg = "No ligands loaded - ChEMBL/PubChem/BindingDB/IUPHAR APIs may be unavailable or targets not found. Check /cancer-research/health/data-sources for API status."
                    result['warnings'].append(warning_msg)
                    result['progress'].append("Step 2/5: ❌ No ligands found (APIs may be unavailable)")
                    result['ligands_loaded'] = 0
        except Exception as e:
            error_msg = f"Error loading ligands: {str(e)}"
            result['errors'].append(error_msg)
            result['warnings'].append("Continuing without ligand data...")
            print(f"⚠️  {error_msg}")
            import traceback
            traceback.print_exc()
        
        # Step 3: Load assays
        print("\n🔬 Step 3: Loading assays...")
        result['progress'].append("Step 3/5: Loading assays from ChEMBL/PubChem...")
        try:
            from assay_loader import load_assays_for_mechanism_targets, get_assays_for_mechanism
            # Check existing count before loading
            existing_assays = get_assays_for_mechanism(mechanism_id, conn)
            existing_count = len(existing_assays)
            print(f"   📊 Existing assays in database: {existing_count}")
            
            assays_result = retry_api_call(
                load_assays_for_mechanism_targets,
                max_retries=2,
                delay=2.0,  # Longer delay for ChEMBL API
                mechanism_id=mechanism_id,
                force_refresh=force_refresh,
                conn=conn
            )
            
            # Check count after loading
            updated_assays = get_assays_for_mechanism(mechanism_id, conn)
            updated_count = len(updated_assays)
            result['assays_loaded'] = assays_result or 0
            
            if updated_count > existing_count:
                newly_loaded = updated_count - existing_count
                print(f"✅ Loaded {newly_loaded} new assays (total: {updated_count})")
                result['progress'].append(f"Step 3/5: ✅ Loaded {newly_loaded} new assays (total: {updated_count})")
                result['assays_loaded'] = newly_loaded
            elif updated_count > 0:
                print(f"⚠️  Assays already exist: {updated_count} total assays found")
                result['warnings'].append(f"Assays already exist: {updated_count} total (no new data loaded)")
                result['progress'].append(f"Step 3/5: ⚠️  {updated_count} assays exist (no new data)")
                result['assays_loaded'] = 0
            else:
                print(f"❌ No assays found after loading attempt")
                warning_msg = "No assays loaded - ChEMBL/PubChem APIs may be unavailable or targets not found. Check /cancer-research/health/data-sources for API status."
                result['warnings'].append(warning_msg)
                result['progress'].append("Step 3/5: ❌ No assays found (APIs may be unavailable)")
                result['assays_loaded'] = 0
        except Exception as e:
            error_msg = f"Error loading assays: {str(e)}"
            result['errors'].append(error_msg)
            result['warnings'].append("Continuing without assay data...")
            print(f"⚠️  {error_msg}")
            import traceback
            traceback.print_exc()
        
        # Step 4: Load drug outcomes
        print("\n💊 Step 4: Loading drug outcomes...")
        result['progress'].append("Step 4/5: Loading drug outcomes...")
        try:
            from drug_outcome_loader import load_drug_outcomes_for_mechanism
            result['outcomes_loaded'] = load_drug_outcomes_for_mechanism(mechanism_id, conn)
            print(f"✅ Loaded {result['outcomes_loaded']} drug outcomes")
            result['progress'].append(f"Step 4/5: ✅ Loaded {result['outcomes_loaded']} drug outcomes")
        except Exception as e:
            error_msg = f"Error loading drug outcomes: {str(e)}"
            result['errors'].append(error_msg)
            result['warnings'].append("Continuing without outcome data...")
            print(f"⚠️  {error_msg}")
            import traceback
            traceback.print_exc()
        
        # Step 5: Load cancer mappings (usually already loaded, but check)
        print("\n🎯 Step 5: Checking cancer mappings...")
        result['progress'].append("Step 5/5: Checking cancer mappings...")
        try:
            from cancer_mapping_loader import get_cancers_for_mechanism
            existing_mappings = get_cancers_for_mechanism(mechanism_id, conn)
            result['cancer_mappings_loaded'] = len(existing_mappings)
            if result['cancer_mappings_loaded'] == 0:
                result['warnings'].append("No cancer mappings found - may need to load manually")
                result['progress'].append("Step 5/5: ⚠️  No cancer mappings found")
            else:
                print(f"✅ Found {result['cancer_mappings_loaded']} cancer mappings")
                result['progress'].append(f"Step 5/5: ✅ Found {result['cancer_mappings_loaded']} cancer mappings")
        except Exception as e:
            error_msg = f"Error checking cancer mappings: {str(e)}"
            result['warnings'].append(error_msg)
            print(f"⚠️  {error_msg}")
        
        print(f"\n✅ ETL complete for mechanism {mechanism_id}")
        print(f"   Targets: {result['targets_loaded']}")
        print(f"   Ligands: {result['ligands_loaded']}")
        print(f"   Assays: {result['assays_loaded']}")
        print(f"   Outcomes: {result['outcomes_loaded']}")
        print(f"   Cancer Mappings: {result['cancer_mappings_loaded']}")
        
        result['progress'].append("✅ ETL pipeline complete")
        
        if result['errors']:
            print(f"\n⚠️  Errors encountered: {len(result['errors'])}")
        if result['warnings']:
            print(f"⚠️  Warnings: {len(result['warnings'])}")
        
        return result
        
    except Exception as e:
        error_msg = f"Fatal error in ETL pipeline: {str(e)}"
        result['errors'].append(error_msg)
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return result
    finally:
        if should_close:
            conn.close()


def retry_api_call(func, max_retries: int = 3, delay: float = 1.0, *args, **kwargs):
    """
    Retry an API call with exponential backoff.
    
    Args:
        func: Function to call
        max_retries: Maximum number of retry attempts
        delay: Initial delay in seconds
        *args, **kwargs: Arguments to pass to func
        
    Returns:
        Result of func call, or None if all retries fail
    """
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ API call failed after {max_retries} attempts: {e}")
                return None
            wait_time = delay * (2 ** attempt)
            print(f"⚠️  API call failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
            time.sleep(wait_time)
    return None


if __name__ == "__main__":
    # Test ETL for a mechanism
    import sys
    if len(sys.argv) > 1:
        mechanism_id = int(sys.argv[1])
        result = load_mechanism_data(mechanism_id, force_refresh=True)
        print("\n📊 ETL Results:")
        print(f"   {result}")
    else:
        print("Usage: python cancer_research_etl.py <mechanism_id>")
