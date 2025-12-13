"""
Generic script to download specific items by name.
Supports molecules, drugs, and diseases.
"""

import argparse
import sys
from pathlib import Path
from typing import List

from download_molecules import download_molecules_by_names
from pubchem_drug_loader import load_drug_info
try:
    from multi_api_disease_loader import search_drugs_by_disease_multi_api
    MULTI_API_AVAILABLE = True
except ImportError:
    MULTI_API_AVAILABLE = False
    try:
        from pubchem_disease_loader import search_drugs_by_disease
    except ImportError:
        search_drugs_by_disease = None
from drugbank_loader import save_drugs_to_db, save_disease_data_to_db
from data_loader import load_from_database, DB_PATH
from top_100_diseases import get_top_100_diseases


def download_molecules(names: List[str]) -> int:
    """
    Download molecules by name.
    
    Args:
        names: List of molecule names
        
    Returns:
        Number of molecules downloaded
    """
    print(f"📥 Downloading {len(names)} molecules by name...")
    df = download_molecules_by_names(names)
    
    if df is None or len(df) == 0:
        return 0
    
    # Save to database
    from data_loader import save_to_database
    existing_df = load_from_database()
    if existing_df is not None and len(existing_df) > 0:
        import pandas as pd
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        # Remove duplicates: first by pubchem_cid (only for non-empty values), then by chembl_id for remaining rows
        if 'pubchem_cid' in combined_df.columns:
            # Separate rows with non-empty pubchem_cid from those without
            has_pubchem = combined_df['pubchem_cid'].notna() & (combined_df['pubchem_cid'] != '')
            df_with_pubchem = combined_df[has_pubchem].copy()
            df_without_pubchem = combined_df[~has_pubchem].copy()
            
            # Deduplicate rows with pubchem_cid by pubchem_cid
            if len(df_with_pubchem) > 0:
                df_with_pubchem = df_with_pubchem.drop_duplicates(subset=['pubchem_cid'], keep='first')
            
            # For rows without pubchem_cid, deduplicate by chembl_id if available
            if len(df_without_pubchem) > 0 and 'chembl_id' in df_without_pubchem.columns:
                df_without_pubchem = df_without_pubchem.drop_duplicates(subset=['chembl_id'], keep='first')
            
            # Recombine
            combined_df = pd.concat([df_with_pubchem, df_without_pubchem], ignore_index=True)
        elif 'chembl_id' in combined_df.columns:
            combined_df = combined_df.drop_duplicates(subset=['chembl_id'], keep='first')
        # else: no deduplication key available, keep all rows
        save_to_database(combined_df)
    else:
        save_to_database(df)
    
    return len(df)


def download_drugs(names: List[str]) -> int:
    """
    Download drugs by name.
    
    Args:
        names: List of drug names
        
    Returns:
        Number of drugs downloaded
    """
    print(f"📥 Downloading {len(names)} drugs by name...")
    
    molecule_df = load_from_database()
    drugs = []
    
    for i, name in enumerate(names, 1):
        name = name.strip()
        if not name:
            continue
        
        print(f"  [{i}/{len(names)}] Downloading: {name}")
        
        try:
            drug_info = load_drug_info(name, molecule_df=molecule_df)
            
            if drug_info:
                drugs.append(drug_info)
                print(f"    ✓ Downloaded: {drug_info.get('name', name)}")
            else:
                print(f"    ⚠️  Not found: {name}")
        
        except Exception as e:
            print(f"    ⚠️  Error downloading '{name}': {e}")
            continue
    
    if drugs:
        save_drugs_to_db(drugs)
        print(f"✅ Downloaded {len(drugs)}/{len(names)} drugs")
        return len(drugs)
    else:
        print("❌ No drugs downloaded")
        return 0


def download_diseases(names: List[str], max_drugs_per_disease: int = 10) -> int:
    """
    Download diseases and their associated drugs.
    
    Args:
        names: List of disease names
        max_drugs_per_disease: Maximum drugs to download per disease
        
    Returns:
        Number of diseases processed
    """
    import time
    import os
    from progress_tracker import write_progress
    
    start_time = time.time()
    task_id = str(os.getpid())
    
    print(f"📥 Downloading {len(names)} diseases and their drugs...")
    print(f"   Target: {max_drugs_per_disease} drugs per disease")
    print(f"   Started at: {time.strftime('%H:%M:%S')}")
    sys.stdout.flush()
    
    write_progress(task_id, 'starting', f'Starting download of {len(names)} diseases', {
        'total_diseases': len(names),
        'max_drugs_per_disease': max_drugs_per_disease
    })
    
    molecule_df = load_from_database()
    relationships = []
    all_drugs = []
    
    for i, disease_name in enumerate(names, 1):
        disease_name = disease_name.strip()
        if not disease_name:
            continue
        
        disease_start = time.time()
        print(f"\n  [{i}/{len(names)}] Processing: {disease_name}")
        print(f"   Progress: {i}/{len(names)} diseases ({i/len(names)*100:.1f}%)")
        sys.stdout.flush()
        
        write_progress(task_id, 'processing', f'Processing disease {i}/{len(names)}: {disease_name}', {
            'current_disease': disease_name,
            'disease_index': i,
            'total_diseases': len(names),
            'progress_percent': i/len(names)*100
        })
        
        try:
            # Search for drugs for this disease using multi-API approach
            search_start = time.time()
            print(f"   🔍 Searching APIs for drugs...")
            sys.stdout.flush()
            
            write_progress(task_id, 'searching', f'Searching APIs for drugs treating {disease_name}...', {
                'current_disease': disease_name,
                'disease_index': i,
                'total_diseases': len(names),
                'stage': 'api_search'
            })
            
            if MULTI_API_AVAILABLE:
                drugs = search_drugs_by_disease_multi_api(disease_name, max_drugs=max_drugs_per_disease)
                # Convert to expected format
                drugs = [{
                    'drug_name': d.get('name') or d.get('generic_name'),
                    'pubchem_cid': d.get('pubchem_cid'),
                    'smiles': d.get('smiles'),
                    'molecular_weight': d.get('molecular_weight'),
                    'disease': disease_name,
                    'source': d.get('api_source', 'multi_api'),
                    'indication': d.get('indication', ''),
                    'description': d.get('description', ''),
                } for d in drugs if d.get('name') or d.get('generic_name')]
            elif search_drugs_by_disease:
                drugs = search_drugs_by_disease(disease_name, max_drugs=max_drugs_per_disease)
            else:
                print(f"    ⚠️  No drug search API available")
                drugs = []
            
            search_time = time.time() - search_start
            print(f"   ⏱️  Search completed in {search_time:.1f}s")
            sys.stdout.flush()
            
            write_progress(task_id, 'searching', f'Found {len(drugs)} potential drugs from APIs', {
                'current_disease': disease_name,
                'drugs_found': len(drugs),
                'search_time': search_time
            })
            
            if drugs:
                print(f"   📦 Found {len(drugs)} potential drugs, loading details...")
                sys.stdout.flush()
                
                write_progress(task_id, 'loading', f'Loading details for {len(drugs)} drugs...', {
                    'current_disease': disease_name,
                    'drugs_to_load': len(drugs),
                    'stage': 'loading_drug_details'
                })
                
                # Load drug information and match to molecules
                loaded_count = 0
                total_to_load = min(len(drugs), max_drugs_per_disease)
                for j, drug_data in enumerate(drugs[:max_drugs_per_disease], 1):
                    if j % 5 == 0 or j == total_to_load:
                        progress_pct = j/total_to_load*100
                        print(f"   📊 Loading drug {j}/{total_to_load} ({progress_pct:.0f}%)...")
                        sys.stdout.flush()
                        
                        write_progress(task_id, 'loading', f'Loading drug {j}/{total_to_load} for {disease_name}...', {
                            'current_disease': disease_name,
                            'drugs_loaded': j,
                            'total_drugs': total_to_load,
                            'load_progress_percent': progress_pct
                        })
                    drug_name = drug_data.get('drug_name')
                    if not drug_name:
                        continue
                    
                    try:
                        # Try to load full drug info (this will match to molecules)
                        drug_info = load_drug_info(drug_name, molecule_df=molecule_df)
                        if drug_info:
                            drug_info['disease'] = disease_name
                            all_drugs.append(drug_info)
                            loaded_count += 1
                            
                            # Create relationship with molecule_index if available
                            molecule_index = drug_info.get('molecule_index')
                            relationships.append({
                                'drug_name': drug_info.get('name'),
                                'smiles': drug_info.get('smiles'),
                                'disease': disease_name,
                                'indication_type': 'approved',
                                'pubchem_cid': drug_info.get('pubchem_cid'),
                                'molecule_index': molecule_index  # Include molecule_index if matched
                            })
                        else:
                            # If load_drug_info fails, still save the drug but without molecule match
                            # This will create a drug record and link via drug_id only
                            from pubchem_drug_loader import fetch_drug_info_from_pubchem
                            pubchem_cid = drug_data.get('pubchem_cid')
                            drug_name_for_search = drug_data.get('name') or drug_data.get('generic_name')
                            if pubchem_cid or drug_name_for_search:
                                try:
                                    drug_details = fetch_drug_info_from_pubchem(drug_name_for_search or '', pubchem_cid)
                                    if drug_details:
                                        drug_details['disease'] = disease_name
                                        all_drugs.append(drug_details)
                                        relationships.append({
                                            'drug_name': drug_name,
                                            'smiles': drug_data.get('smiles'),
                                            'disease': disease_name,
                                            'indication_type': 'approved',
                                            'pubchem_cid': pubchem_cid,
                                            'molecule_index': None  # No molecule match yet
                                        })
                                except Exception as fetch_err:
                                    # Fallback fetch failed; continue with other drugs
                                    # Optionally: print(f"      ⚠️  Fallback fetch failed for '{drug_name}': {fetch_err}")
                                    pass
                    except Exception as e:
                        print(f"    ⚠️  Error loading drug '{drug_name}': {e}")
                        continue
                
                disease_time = time.time() - disease_start
                matched_count = len([d for d in relationships if d.get('disease') == disease_name])
                print(f"   ✅ Completed {disease_name} in {disease_time:.1f}s")
                print(f"   📊 Results: {loaded_count} drugs loaded, {matched_count} relationships created")
                sys.stdout.flush()
                
                write_progress(task_id, 'processing', f'Completed {disease_name}: {loaded_count} drugs loaded', {
                    'current_disease': disease_name,
                    'disease_index': i,
                    'total_diseases': len(names),
                    'drugs_loaded': loaded_count,
                    'relationships_created': matched_count,
                    'disease_time': disease_time
                })
            else:
                print(f"    ⚠️  No drugs found for {disease_name}")
                sys.stdout.flush()
        
        except Exception as e:
            print(f"    ⚠️  Error processing '{disease_name}': {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if relationships:
        save_start = time.time()
        print(f"\n💾 Saving to database...")
        sys.stdout.flush()
        
        write_progress(task_id, 'saving', 'Saving to database...', {
            'relationships_to_save': len(relationships),
            'drugs_to_save': len(all_drugs)
        })
        
        save_disease_data_to_db(relationships, molecule_df, drugs=all_drugs if all_drugs else None)
        save_time = time.time() - save_start
        
        total_time = time.time() - start_time
        diseases_processed = len(set(r.get('disease') for r in relationships))
        drugs_saved = len(all_drugs)
        relationships_saved = len(relationships)
        
        print(f"\n✅ Download complete!")
        print(f"   Diseases processed: {diseases_processed}")
        print(f"   Drugs saved: {drugs_saved}")
        print(f"   Relationships created: {relationships_saved}")
        print(f"   Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
        print(f"   Average per disease: {total_time/len(names):.1f}s")
        sys.stdout.flush()
        
        write_progress(task_id, 'completed', 'Download completed successfully', {
            'diseases_processed': diseases_processed,
            'drugs_saved': drugs_saved,
            'relationships_created': relationships_saved,
            'total_time': total_time,
            'save_time': save_time
        })
        
        return diseases_processed
    else:
        write_progress(task_id, 'failed', 'No relationships created', {})
        print("❌ No diseases processed")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description='Download specific items by name',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download molecules by name
  python download_by_name.py molecules --names "aspirin,ibuprofen"
  
  # Download drugs by name
  python download_by_name.py drugs --names "donepezil,rivastigmine"
  
  # Download diseases by name
  python download_by_name.py diseases --names "Alzheimer's disease,diabetes"
        """
    )
    
    subparsers = parser.add_subparsers(dest='type', help='Type of item to download')
    
    # Molecules parser
    molecules_parser = subparsers.add_parser('molecules', help='Download molecules')
    molecules_parser.add_argument('--names', type=str, required=True,
                                 help='Comma-separated list of molecule names')
    
    # Drugs parser
    drugs_parser = subparsers.add_parser('drugs', help='Download drugs')
    drugs_parser.add_argument('--names', type=str, required=True,
                             help='Comma-separated list of drug names')
    
    # Diseases parser
    diseases_parser = subparsers.add_parser('diseases', help='Download diseases')
    diseases_parser.add_argument('--names', type=str, required=True,
                                help='Comma-separated list of disease names')
    diseases_parser.add_argument('--max-drugs', type=int, default=10,
                                help='Maximum drugs per disease (default: 10)')
    
    args = parser.parse_args()
    
    if not args.type:
        parser.print_help()
        sys.exit(1)
    
    # Parse names
    names = [n.strip() for n in args.names.split(',')]
    
    # Download based on type
    if args.type == 'molecules':
        count = download_molecules(names)
        print(f"\n✅ Downloaded {count} molecules")
    elif args.type == 'drugs':
        count = download_drugs(names)
        print(f"\n✅ Downloaded {count} drugs")
    elif args.type == 'diseases':
        count = download_diseases(names, max_drugs_per_disease=args.max_drugs)
        print(f"\n✅ Processed {count} diseases")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Download interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error during download: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

