"""
CLI script to download molecules from PubChem.
Supports downloading by count or by name list.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

try:
    import pubchempy as pcp
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False


def retry_with_backoff(func, max_retries=5, base_delay=1.0, max_delay=60.0):
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry (should raise an exception on failure)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        
    Returns:
        Result of the function call
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_str = str(e)
            # Check if it's a rate limit error
            is_rate_limit = (
                "503" in error_str or
                "ServerBusy" in error_str or
                "Too many requests" in error_str or
                "rate limit" in error_str.lower() or
                "PUGREST.ServerBusy" in error_str
            )
            
            if not is_rate_limit and attempt < max_retries - 1:
                # Not a rate limit error, retry immediately
                continue
            
            if attempt < max_retries - 1:
                # Calculate exponential backoff delay
                delay = min(base_delay * (2 ** attempt), max_delay)
                if is_rate_limit:
                    print(f"  ⚠️  Rate limited, waiting {delay:.1f}s before retry ({attempt + 1}/{max_retries})...")
                else:
                    print(f"  ⚠️  Error, retrying in {delay:.1f}s ({attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                # Last attempt failed
                raise
    raise Exception("Max retries exceeded")

from rdkit import Chem
try:
    from .data_loader import DB_PATH, save_to_database, load_from_database
except ImportError:
    try:
        from data_loader import DB_PATH, save_to_database, load_from_database
    except ImportError:
        from backend.data_loader import DB_PATH, save_to_database, load_from_database
import pandas as pd
import sqlite3


def download_molecules_by_count(count: Optional[int] = None, source: str = "pubchem", use_ftp: bool = True, full_file: Optional[bool] = None) -> pd.DataFrame:
    """
    Download molecules by count from specified source.
    
    Args:
        count: Number of molecules to download (None = all from downloaded files, required if full_file is False/None)
        source: Source to use ("pubchem", "chembl", "zinc")
        use_ftp: If True and source is pubchem, use FTP instead of API (avoids rate limits)
        full_file: If True, download complete SDF files and import all molecules (ignores count)
        
    Returns:
        DataFrame with downloaded molecules
    """
    # Validate inputs
    if full_file is True:
        # If full_file is provided, ignore count
        if source == "pubchem" and use_ftp:
            print(f"📥 Downloading full file from PubChem FTP (no rate limits)...")
            return download_from_pubchem_ftp(count=None, full_file=True)
        else:
            print("❌ Full file download is only supported for PubChem FTP")
            return pd.DataFrame()
    elif full_file is False or full_file is None:
        # If full_file is not True, require count to be a positive int
        if count is None:
            print("❌ Error: count must be provided when full_file is not True")
            return pd.DataFrame()
        if not isinstance(count, int) or count <= 0:
            print(f"❌ Error: count must be a positive integer, got: {count}")
            return pd.DataFrame()
    
    if source == "pubchem":
        if use_ftp:
            print(f"📥 Downloading {count} molecules from PubChem FTP (no rate limits)...")
            return download_from_pubchem_ftp(count=count, full_file=False)
        else:
            if not PUBCHEM_AVAILABLE:
                print("❌ PubChem not available. Install with: pip install pubchempy")
                return pd.DataFrame()
            print(f"📥 Downloading {count} molecules from PubChem API...")
            return download_from_pubchem(count)
    elif source == "chembl":
        print("⚠️  ChEMBL download not yet implemented in this script")
        print("   Use 'python backend/main.py setup' for ChEMBL downloads")
        return pd.DataFrame()
    elif source == "zinc":
        print("⚠️  ZINC download not yet implemented in this script")
        print("   Use 'python backend/main.py setup' for ZINC downloads")
        return pd.DataFrame()
    else:
        print(f"❌ Unknown source: {source}")
        return pd.DataFrame()


def download_from_pubchem_ftp(count: Optional[int] = None, full_file: bool = False) -> pd.DataFrame:
    """
    Download molecules from PubChem using FTP (no rate limits!).
    
    Args:
        count: Number of molecules to download (None = all from downloaded files)
        full_file: If True, download complete SDF files and import all molecules
        
    Returns:
        DataFrame with molecules
    """
    import subprocess
    import sys
    from pathlib import Path
    
    print(f"🌐 Using PubChem FTP: ftp.ncbi.nlm.nih.gov/pubchem/Compound/")
    print(f"   This avoids API rate limits and is much faster for bulk downloads")
    
    # Use the existing FTP download script
    script_path = Path(__file__).parent / "download_pubchem_ftp.py"
    output_file = Path(__file__).parent.parent / "data" / "downloads" / "pubchem_compounds.smi"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"📥 Running FTP downloader...")
        if full_file:
            print(f"   Mode: Full file download - will import ALL molecules from downloaded SDF file")
            print(f"   Each file contains ~500,000 compounds and is 300-500 MB")
        else:
            print(f"   This may take a few minutes - downloading and converting SDF files")
        print(f"   You'll see progress updates below:\n")
        print("=" * 60)
        
        # Build command
        cmd = [sys.executable, str(script_path), "--output", str(output_file)]
        if full_file:
            cmd.append("--full-file")
        elif count:
            cmd.extend(["--max-molecules", str(count)])
        
        # Run with real-time output streaming
        # Using check=False to handle errors manually and provide better feedback
        result = subprocess.run(
            cmd,
            # Don't capture output - let it stream in real-time
            timeout=3600,  # 60 minute timeout for full file downloads
            check=False  # Don't raise on non-zero exit, handle manually
        )
        
        print("=" * 60)
        print()
        
        if result.returncode == 0:
            # Parse the downloaded SMILES file
            if output_file.exists():
                print(f"✅ FTP download completed, parsing SMILES file...")
                return parse_ftp_smiles_file(output_file, count)
            else:
                print(f"⚠️  Output file not found: {output_file}")
                return pd.DataFrame()
        else:
            print(f"⚠️  FTP download failed (exit code: {result.returncode})")
            # Fall back to API if FTP fails
            if count is None:
                return pd.DataFrame()
            print("   Falling back to PubChem API (with retry logic)...")
            return download_from_pubchem(count)
    
    except subprocess.TimeoutExpired:
        print("⚠️  FTP download timed out (may be downloading large files)")
        if count is None:
            return pd.DataFrame()
        print("   Falling back to PubChem API (with retry logic)...")
        return download_from_pubchem(count)
    except Exception as e:
        print(f"⚠️  FTP download error: {e}")
        if count is None:
            return pd.DataFrame()
        print("   Falling back to PubChem API (with retry logic)...")
        return download_from_pubchem(count)


def parse_ftp_smiles_file(file_path: Path, max_molecules: Optional[int]) -> pd.DataFrame:
    """
    Parse SMILES file downloaded from PubChem FTP.
    
    Args:
        file_path: Path to SMILES file
        max_molecules: Maximum number of molecules to parse
        
    Returns:
        DataFrame with molecules
    """
    molecules_data = []
    seen_cids = set()
    
    # Load existing molecules to avoid duplicates
    existing_df = load_from_database()
    if existing_df is not None and 'pubchem_cid' in existing_df.columns:
        existing_cids = set(existing_df['pubchem_cid'].dropna().astype(str))
        seen_cids.update(existing_cids)
    
    print(f"📖 Parsing SMILES file: {file_path}")
    
    with open(file_path, 'r') as f:
        for _line_num, line in enumerate(f, 1):
            if max_molecules is not None and len(molecules_data) >= max_molecules:
                break
            
            line = line.strip()
            if not line:
                continue
            
            # Try tab-separated format: CID\tSMILES\tName
            parts = line.split('\t')
            if len(parts) >= 2:
                cid = parts[0].strip()
                smiles = parts[1].strip()
                name = parts[2].strip() if len(parts) > 2 else f"PubChem_{cid}"
            else:
                # Try space-separated
                parts = line.split()
                if len(parts) >= 2:
                    cid = parts[0].strip()
                    smiles = parts[1].strip()
                    name = f"PubChem_{cid}"
                else:
                    continue
            
            if not cid or not smiles or str(cid) in seen_cids:
                continue
            
            try:
                # Validate SMILES
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    continue
                
                mw = Chem.rdMolDescriptors.CalcExactMolWt(mol)
                
                # Filter for drug-like molecules
                if mw < 100 or mw > 1000:
                    continue
                
                molecules_data.append({
                    'chembl_id': f"PUBCHEM_{cid}",
                    'smiles': smiles,
                    'name': name,
                    'molecular_weight': mw,
                    'is_approved': False,
                    'targets': [],
                    'formula': '',
                    'inchi': '',
                    'inchikey': '',
                    'pubchem_cid': str(cid)
                })
                seen_cids.add(str(cid))
                
                if len(molecules_data) % 100 == 0:
                    print(f"  ✓ Parsed {len(molecules_data)}/{max_molecules} molecules...")
            
            except Exception as e:
                continue
    
    print(f"✅ Parsed {len(molecules_data)} molecules from FTP download")
    
    if molecules_data:
        return pd.DataFrame(molecules_data)
    else:
        return pd.DataFrame()


def download_from_pubchem(count: int) -> pd.DataFrame:
    """
    Download molecules from PubChem.
    
    Args:
        count: Number of molecules to download
        
    Returns:
        DataFrame with molecules
    """
    if not PUBCHEM_AVAILABLE:
        print("❌ PubChem not available. Install with: pip install pubchempy")
        return pd.DataFrame()
    
    molecules_data = []
    seen_cids = set()
    
    # Load existing molecules to avoid duplicates
    existing_df = load_from_database()
    if existing_df is not None and 'pubchem_cid' in existing_df.columns:
        existing_cids = set(existing_df['pubchem_cid'].dropna().astype(str))
        seen_cids.update(existing_cids)
        print(f"📊 Found {len(seen_cids)} existing molecules in database")
    
    # Common drug names to search
    drug_names = [
        "aspirin", "ibuprofen", "acetaminophen", "naproxen", "diclofenac",
        "penicillin", "amoxicillin", "azithromycin", "cephalexin", "ciprofloxacin",
        "atorvastatin", "lisinopril", "amlodipine", "metoprolol", "losartan",
        "simvastatin", "hydrochlorothiazide", "furosemide", "carvedilol", "clopidogrel",
        "metformin", "insulin", "glipizide", "pioglitazone", "sitagliptin",
        "sertraline", "escitalopram", "fluoxetine", "bupropion", "trazodone",
        "warfarin", "levothyroxine", "omeprazole", "albuterol", "gabapentin",
        "tramadol", "hydrocodone", "oxycodone", "morphine", "codeine",
        "prednisone", "tamsulosin", "fluticasone", "montelukast", "pantoprazole",
        "venlafaxine", "quetiapine", "aripiprazole", "olanzapine",
        "donepezil", "rivastigmine", "galantamine", "memantine",
        "tacrine", "physostigmine", "neostigmine"
    ]
    
    print(f"🔍 Searching PubChem for molecules...")
    print(f"   Using retry logic with exponential backoff for rate limits")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    for name in drug_names:
        if len(molecules_data) >= count:
            break
        
        # If we've had too many consecutive errors, wait longer
        if consecutive_errors >= max_consecutive_errors:
            wait_time = min(30.0, 5.0 * consecutive_errors)
            print(f"  ⚠️  Too many consecutive errors, waiting {wait_time:.1f}s before continuing...")
            time.sleep(wait_time)
            consecutive_errors = 0
        
        try:
            # Use retry logic for the API call
            compounds = retry_with_backoff(
                lambda: pcp.get_compounds(name, 'name'),
                max_retries=3,
                base_delay=2.0,
                max_delay=30.0
            )
            consecutive_errors = 0  # Reset on success
            
            for comp in compounds:
                if len(molecules_data) >= count:
                    break
                
                cid = comp.cid
                if not cid or str(cid) in seen_cids:
                    continue
                
                try:
                    smiles = comp.connectivity_smiles or comp.isomeric_smiles or getattr(comp, 'canonical_smiles', None)
                    if not smiles:
                        continue
                    
                    # Validate SMILES
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        continue
                    
                    mw = comp.molecular_weight or 0
                    
                    # Filter for drug-like molecules
                    if mw < 100 or mw > 1000:
                        continue
                    
                    name_val = comp.iupac_name
                    if not name_val and comp.synonyms:
                        name_val = comp.synonyms[0]
                    if not name_val:
                        name_val = f"PubChem_{cid}"
                    
                    molecules_data.append({
                        'chembl_id': f"PUBCHEM_{cid}",
                        'smiles': smiles,
                        'name': name_val,
                        'molecular_weight': mw,
                        'is_approved': True,
                        'targets': [],
                        'formula': comp.molecular_formula or '',
                        'inchi': '',
                        'inchikey': '',
                        'pubchem_cid': str(cid)
                    })
                    seen_cids.add(str(cid))
                    
                    if len(molecules_data) % 10 == 0:
                        print(f"  ✓ Downloaded {len(molecules_data)}/{count} molecules...")
                    
                    # Adaptive rate limiting - longer delay if we've had errors
                    delay = 0.5 + (0.2 * consecutive_errors)
                    time.sleep(min(delay, 2.0))  # Cap at 2 seconds
                
                except Exception as e:
                    continue
        
        except Exception as e:
            error_str = str(e)
            is_rate_limit = (
                "503" in error_str or
                "ServerBusy" in error_str or
                "Too many requests" in error_str or
                "PUGREST.ServerBusy" in error_str
            )
            
            if is_rate_limit:
                consecutive_errors += 1
                print(f"  ⚠️  Rate limited for '{name}': {error_str[:80]}")
                # Wait longer on rate limit
                time.sleep(min(5.0 + (2.0 * consecutive_errors), 30.0))
            else:
                print(f"  ⚠️  Error searching for '{name}': {error_str[:80]}")
                consecutive_errors += 1
            continue
    
    print(f"✅ Downloaded {len(molecules_data)} molecules from PubChem")
    
    if molecules_data:
        df = pd.DataFrame(molecules_data)
        return df
    else:
        return pd.DataFrame()


def download_molecules_by_names(names: List[str]) -> pd.DataFrame:
    """
    Download specific molecules by name list.
    
    Args:
        names: List of molecule names to download
        
    Returns:
        DataFrame with downloaded molecules
    """
    if not PUBCHEM_AVAILABLE:
        print("❌ PubChem not available. Install with: pip install pubchempy")
        return pd.DataFrame()
    
    print(f"📥 Downloading {len(names)} molecules by name from PubChem...")
    
    molecules_data = []
    seen_cids = set()
    
    # Load existing molecules
    existing_df = load_from_database()
    if existing_df is not None and 'pubchem_cid' in existing_df.columns:
        existing_cids = set(existing_df['pubchem_cid'].dropna().astype(str))
        seen_cids.update(existing_cids)
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    for i, name in enumerate(names, 1):
        name = name.strip()
        if not name:
            continue
        
        # If we've had too many consecutive errors, wait longer
        if consecutive_errors >= max_consecutive_errors:
            wait_time = min(30.0, 5.0 * consecutive_errors)
            print(f"  ⚠️  Too many consecutive errors, waiting {wait_time:.1f}s before continuing...")
            time.sleep(wait_time)
            consecutive_errors = 0
        
        print(f"  [{i}/{len(names)}] Searching for: {name}")
        
        try:
            # Use retry logic for the API call
            compounds = retry_with_backoff(
                lambda: pcp.get_compounds(name, 'name'),
                max_retries=3,
                base_delay=2.0,
                max_delay=30.0
            )
            consecutive_errors = 0  # Reset on success
            
            if not compounds:
                print(f"    ⚠️  No compounds found for '{name}'")
                continue
            
            comp = compounds[0]  # Take first result
            cid = comp.cid
            
            if not cid or str(cid) in seen_cids:
                if str(cid) in seen_cids:
                    print(f"    ℹ️  Already exists in database (CID: {cid})")
                continue
            
            try:
                smiles = comp.connectivity_smiles or comp.isomeric_smiles or getattr(comp, 'canonical_smiles', None)
                if not smiles:
                    print(f"    ⚠️  No SMILES found for '{name}'")
                    continue
                
                # Validate SMILES
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    print(f"    ⚠️  Invalid SMILES for '{name}'")
                    continue
                
                mw = comp.molecular_weight or 0
                
                name_val = comp.iupac_name
                if not name_val and comp.synonyms:
                    name_val = comp.synonyms[0]
                if not name_val:
                    name_val = name
                
                molecules_data.append({
                    'chembl_id': f"PUBCHEM_{cid}",
                    'smiles': smiles,
                    'name': name_val,
                    'molecular_weight': mw,
                    'is_approved': True,
                    'targets': [],
                    'formula': comp.molecular_formula or '',
                    'inchi': '',
                    'inchikey': '',
                    'pubchem_cid': str(cid)
                })
                seen_cids.add(str(cid))
                print(f"    ✓ Downloaded: {name_val}")
            
            except Exception as e:
                print(f"    ⚠️  Error processing '{name}': {e}")
                continue
            
            # Adaptive rate limiting
            delay = 0.5 + (0.2 * consecutive_errors)
            time.sleep(min(delay, 2.0))  # Cap at 2 seconds
        
        except Exception as e:
            error_str = str(e)
            is_rate_limit = (
                "503" in error_str or
                "ServerBusy" in error_str or
                "Too many requests" in error_str or
                "PUGREST.ServerBusy" in error_str
            )
            
            if is_rate_limit:
                consecutive_errors += 1
                print(f"    ⚠️  Rate limited for '{name}': {error_str[:80]}")
                # Wait longer on rate limit
                time.sleep(min(5.0 + (2.0 * consecutive_errors), 30.0))
            else:
                print(f"    ⚠️  Error searching for '{name}': {error_str[:80]}")
                consecutive_errors += 1
            continue
    
    print(f"✅ Downloaded {len(molecules_data)}/{len(names)} molecules")
    
    if molecules_data:
        df = pd.DataFrame(molecules_data)
        return df
    else:
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(
        description='Download molecules from PubChem',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download 1000 molecules
  python download_molecules.py --count 1000
  
  # Download specific molecules by name
  python download_molecules.py --names "aspirin,ibuprofen,acetaminophen"
  
  # Download from specific source
  python download_molecules.py --count 500 --source pubchem
        """
    )
    
    parser.add_argument(
        '--count',
        type=int,
        default=None,
        help='Number of molecules to download (default: None = all from downloaded files)'
    )
    
    parser.add_argument(
        '--full-file',
        action='store_true',
        help='Download complete SDF files and import all molecules (FTP only, ignores --count)'
    )
    
    parser.add_argument(
        '--names',
        type=str,
        help='Comma-separated list of molecule names to download'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default='pubchem',
        choices=['pubchem', 'chembl', 'zinc'],
        help='Data source to use (default: pubchem)'
    )
    
    parser.add_argument(
        '--use-api',
        action='store_true',
        help='Use PubChem API instead of FTP (may hit rate limits)'
    )
    
    args = parser.parse_args()
    
    if not args.count and not args.names and not args.full_file:
        parser.error("Either --count, --names, or --full-file must be specified")
    
    # Load existing database
    print("📂 Loading existing database...")
    existing_df = load_from_database()
    if existing_df is not None:
        print(f"✅ Found {len(existing_df)} existing molecules")
    else:
        print("ℹ️  No existing database found")
    
    # Download molecules
    if args.names:
        names_list = [n.strip() for n in args.names.split(',')]
        df = download_molecules_by_names(names_list)
    else:
        # Use FTP by default for pubchem (avoids rate limits), unless --use-api is specified
        use_ftp = not args.use_api if args.source == 'pubchem' else False
        df = download_molecules_by_count(args.count, args.source, use_ftp=use_ftp, full_file=args.full_file)
    
    # Handle case where no molecules were downloaded
    if df is None or len(df) == 0:
        print("⚠️  No new molecules downloaded (may already exist in database)")
        if existing_df is not None:
            print(f"ℹ️  Current database has {len(existing_df)} molecules")
        print("=" * 60)
        print("✅ Download process completed (no new molecules)")
        print("=" * 60)
        return
    
    # Merge with existing data
    new_count = len(df)
    if existing_df is not None and len(existing_df) > 0:
        # Combine dataframes, avoiding duplicates
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
        
        new_count = len(combined_df) - len(existing_df)
        print(f"✅ Combined with existing data: {len(combined_df)} total molecules ({new_count} new)")
        df = combined_df
    else:
        print(f"✅ Downloaded {new_count} new molecules")
    
    # Save to database
    if new_count > 0 or existing_df is None:
        print("💾 Saving to database...")
        save_to_database(df)
    
    print("\n" + "=" * 60)
    print("✅ Molecule Download Complete")
    print("=" * 60)
    print(f"Molecules in database: {len(df)}")
    if new_count == 0:
        print("ℹ️  No new molecules added (all already existed)")
    print("=" * 60)


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

