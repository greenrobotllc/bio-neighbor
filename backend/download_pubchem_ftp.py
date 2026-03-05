#!/usr/bin/env python3
"""
Download PubChem compounds using FTP.
PubChem provides bulk downloads via FTP (see https://pubchem.ncbi.nlm.nih.gov/docs/downloads)

Usage:
    python download_pubchem_ftp.py [--max-molecules 10000] [--output data/downloads/pubchem_compounds.smi]

Examples:
    # Download and convert 10,000 compounds
    python download_pubchem_ftp.py --max-molecules 10000

    # Download specific compound list (e.g., FDA drugs)
    python download_pubchem_ftp.py --compound-list <list_id> --max-molecules 10000
"""

import argparse
import sys
from pathlib import Path
import ftplib
import gzip
import tempfile
import shutil
import time
from typing import List, Optional

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# PubChem FTP configuration
PUBCHEM_FTP_HOST = "ftp.ncbi.nlm.nih.gov"
PUBCHEM_FTP_BASE = "/pubchem/Compound/CURRENT-Full/SDF"  # Using CURRENT-Full for latest data
PUBCHEM_COMPOUND_LISTS = "/pubchem/Compound/Monthly/YYYY-MM-01/Compound_000500001_000525000.sdf.gz"

def download_sdf_file(ftp: ftplib.FTP, remote_path: str, local_path: Path, max_retries: int = 3):
    """Download a single SDF file from PubChem FTP with progress feedback and integrity checking."""
    file_size = 0
    try:
        file_size = ftp.size(remote_path)
    except:
        pass
    
    for attempt in range(max_retries):
        downloaded = 0
        
        def callback(data):
            nonlocal downloaded
            downloaded += len(data)
            if file_size > 0:
                downloaded_mb = downloaded / (1024 * 1024)
                total_mb = file_size / (1024 * 1024)
                remaining_mb = total_mb - downloaded_mb
                percent = (downloaded / file_size) * 100
                if downloaded % (1024 * 1024) == 0:  # Print every MB
                    print(f"      📥 {downloaded_mb:.1f} MB / {total_mb:.1f} MB ({percent:.1f}%) | {remaining_mb:.1f} MB remaining", end='\r')
            else:
                # File size unknown, just show downloaded
                if downloaded % (1024 * 1024) == 0:
                    downloaded_mb = downloaded / (1024 * 1024)
                    print(f"      📥 Downloaded: {downloaded_mb:.1f} MB...", end='\r')
            return f.write(data)
        
        try:
            with open(local_path, 'wb') as f:
                ftp.retrbinary(f'RETR {remote_path}', callback)
            
            if file_size > 0:
                print()  # New line after progress
                # Verify file size matches
                actual_size = local_path.stat().st_size
                if actual_size != file_size:
                    print(f"   ⚠️  File size mismatch: expected {file_size} bytes, got {actual_size}")
                    if attempt < max_retries - 1:
                        print(f"   🔄 Retrying download (attempt {attempt + 2}/{max_retries})...")
                        local_path.unlink(missing_ok=True)
                        continue
                    return False
                print(f"   ✅ File size verified: {actual_size / (1024*1024):.1f} MB")
            
            # Try to verify it's a valid gzip file
            try:
                with gzip.open(local_path, 'rb') as test_f:
                    test_f.read(1024)  # Read first 1KB to verify it's valid gzip
                return True
            except Exception as gzip_error:
                print(f"   ⚠️  Gzip validation failed: {gzip_error}")
                if attempt < max_retries - 1:
                    print(f"   🔄 Retrying download (attempt {attempt + 2}/{max_retries})...")
                    local_path.unlink(missing_ok=True)
                    continue
                return False
                
        except Exception as e:
            print(f"\n   ❌ Error downloading {remote_path}: {e}")
            if attempt < max_retries - 1:
                print(f"   🔄 Retrying download (attempt {attempt + 2}/{max_retries})...")
                local_path.unlink(missing_ok=True)
                time.sleep(2)  # Wait before retry
                continue
            return False
    
    return False

def sdf_to_smiles(sdf_path: Path, max_molecules: Optional[int] = None, show_progress: bool = True) -> List[dict]:
    """
    Convert SDF file to SMILES format.
    
    Args:
        sdf_path: Path to SDF file
        max_molecules: Maximum number of molecules to extract
        
    Returns:
        List of molecule dictionaries
    """
    if not RDKIT_AVAILABLE:
        raise ImportError("RDKit is required. Install with: pip install rdkit")
    
    molecules = []
    print(f"   Converting SDF to SMILES: {sdf_path.name}")
    
    try:
        # RDKit can read SDF files
        supplier = Chem.SDMolSupplier(str(sdf_path))
        
        total_processed = 0
        for i, mol in enumerate(supplier):
            if max_molecules and len(molecules) >= max_molecules:
                break
            
            total_processed += 1
            if show_progress and total_processed % 1000 == 0:
                print(f"      Processed {total_processed} compounds, found {len(molecules)} valid...", end='\r')
            
            if mol is None:
                continue
            
            try:
                # Get SMILES (prefer canonical from properties, fallback to RDKit)
                smiles = None
                if mol.HasProp("PUBCHEM_CANONICAL_SMILES"):
                    smiles = mol.GetProp("PUBCHEM_CANONICAL_SMILES")
                else:
                    smiles = Chem.MolToSmiles(mol)
                
                if not smiles:
                    continue
                
                # Get molecular weight
                mw = Descriptors.MolWt(mol)
                
                # Filter for drug-like molecules (MW 150-800)
                if mw < 150 or mw > 800:
                    continue
                
                # Try to get compound ID from properties
                cid = None
                if mol.HasProp("PUBCHEM_COMPOUND_CID"):
                    cid = mol.GetProp("PUBCHEM_COMPOUND_CID")
                elif mol.HasProp("_Name"):
                    name = mol.GetProp("_Name")
                    if name.startswith("CID"):
                        cid = name.replace("CID", "").strip()
                
                # Extract molecule name (prioritize: IUPAC > traditional IUPAC > common name > CID-based)
                name = ""
                if mol.HasProp("PUBCHEM_IUPAC_NAME"):
                    name = mol.GetProp("PUBCHEM_IUPAC_NAME")
                elif mol.HasProp("PUBCHEM_IUPAC_TRADITIONAL_NAME"):
                    name = mol.GetProp("PUBCHEM_IUPAC_TRADITIONAL_NAME")
                elif mol.HasProp("PUBCHEM_PREFERRED_NAME"):
                    name = mol.GetProp("PUBCHEM_PREFERRED_NAME")
                elif mol.HasProp("_Name"):
                    name_prop = mol.GetProp("_Name")
                    if not name_prop.startswith("CID"):
                        name = name_prop
                
                # Extract molecular formula
                formula = ""
                if mol.HasProp("PUBCHEM_MOLECULAR_FORMULA"):
                    formula = mol.GetProp("PUBCHEM_MOLECULAR_FORMULA")
                
                # Extract InChI
                inchi = ""
                if mol.HasProp("PUBCHEM_INCHI"):
                    inchi = mol.GetProp("PUBCHEM_INCHI")
                
                # Extract InChIKey
                inchikey = ""
                if mol.HasProp("PUBCHEM_INCHI_KEY"):
                    inchikey = mol.GetProp("PUBCHEM_INCHI_KEY")
                
                molecules.append({
                    'id': cid or f"PUBCHEM_{i}",
                    'smiles': smiles,
                    'molecular_weight': mw,
                    'name': name,
                    'formula': formula,
                    'inchi': inchi,
                    'inchikey': inchikey,
                    'pubchem_cid': cid
                })
                
                if len(molecules) % 100 == 0:
                    print(f"     ✓ Extracted {len(molecules)} molecules...")
            
            except Exception:
                continue
        
        if show_progress:
            print()  # New line after progress
        print(f"   ✅ Extracted {len(molecules)} valid molecules")
        return molecules
    
    except Exception as e:
        print(f"   ❌ Error converting SDF: {e}")
        return []

def download_pubchem_compounds(max_molecules: Optional[int] = None, output_file: Path = None, download_full_files: bool = False):
    """
    Download PubChem compounds via FTP and convert to SMILES.
    
    Args:
        max_molecules: Maximum number of molecules to download (None = all from downloaded files)
        output_file: Output SMILES file path
        download_full_files: If True, download entire SDF files and import all molecules
    """
    print("=" * 60)
    print("📥 PubChem FTP Download")
    print("=" * 60)
    print(f"Target: {max_molecules} molecules")
    print(f"Host: {PUBCHEM_FTP_HOST}")
    print(f"Path: {PUBCHEM_FTP_BASE}")
    print(f"   (Using CURRENT-Full for latest compound data)")
    print("=" * 60)
    
    if output_file is None:
        output_file = Path("data/downloads/pubchem_compounds.smi")
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to FTP
    print("\n🔌 Connecting to PubChem FTP server...")
    try:
        ftp = ftplib.FTP(PUBCHEM_FTP_HOST)
        ftp.login()  # Anonymous login
        print("✅ Connected successfully")
    except Exception as e:
        print(f"❌ Error connecting to FTP: {e}")
        return False
    
    try:
        # Change to compound directory
        print(f"\n📂 Navigating to: {PUBCHEM_FTP_BASE}")
        ftp.cwd(PUBCHEM_FTP_BASE)
        print("✅ Directory found")
        
        # List available files
        print("\n📋 Listing available SDF files...")
        files = []
        ftp.retrlines('LIST', files.append)
        
        # Filter for SDF files
        sdf_files = [f.split()[-1] for f in files if f.endswith('.sdf.gz')]
        
        if not sdf_files:
            print("❌ No SDF files found in this directory")
            return False
        
        print(f"✅ Found {len(sdf_files)} SDF files")
        print(f"   Note: Each file contains thousands of compounds")
        print(f"   ⚠️  File Size: Each SDF file is 300-500 MB (compressed)")
        print(f"   ⚠️  Compounds per file: ~500,000 compounds per file")
        print(f"   💾 Disk Space: Ensure you have 2-3 GB free space available")
        print(f"   We'll download files until we have {max_molecules} molecules")
        
        # Determine download strategy
        if download_full_files:
            # Download full files - start with 1 file, user can download more later
            files_to_download = 1
            print(f"\n📊 Download plan:")
            print(f"   - Will download 1 complete SDF file")
            print(f"   - All molecules from the file will be imported")
            print(f"   - File size: 300-500 MB (compressed)")
            print(f"   - Compounds: ~500,000 compounds per file")
            print(f"   - Disk space needed: ~1 GB for download + processing")
            print(f"   ⚠️  Downloads happen in chunks - one large file at a time")
        else:
            # Calculate how many files we need (estimate: ~5000 compounds per file)
            estimated_compounds_per_file = 5000
            if max_molecules:
                files_needed = max(1, (max_molecules // estimated_compounds_per_file) + 1)
                files_to_download = min(files_needed, len(sdf_files), 10)  # Cap at 10 files max
            else:
                files_to_download = 1  # Default to 1 file if no limit specified
            
            print(f"\n📊 Download plan:")
            print(f"   - Will download up to {files_to_download} SDF file(s)")
            print(f"   - File size per file: 300-500 MB (compressed)")
            print(f"   - Estimated compounds per file: ~{estimated_compounds_per_file}")
            print(f"   - Total disk space needed: ~{files_to_download * 500} MB - {files_to_download * 1000} MB")
            if max_molecules:
                print(f"   - Target: {max_molecules} molecules")
            else:
                print(f"   - Will import all valid molecules from downloaded files")
            print(f"   ⚠️  Note: Each SDF file is typically 300-500 MB in size")
            print(f"   ⚠️  Downloads happen in chunks - one large file at a time")
        
        # Download files to get enough molecules
        molecules = []
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            print(f"\n⬇️  Starting download...")
            
            for i, sdf_file in enumerate(sdf_files[:files_to_download], 1):
                if max_molecules and len(molecules) >= max_molecules:
                    print(f"\n✅ Reached target of {max_molecules} molecules!")
                    break
                
                print(f"\n[{i}/{files_to_download}] Processing: {sdf_file}")
                local_gz = temp_dir / sdf_file
                local_sdf = temp_dir / sdf_file.replace('.gz', '')
                
                # Download
                print(f"   📥 Downloading file ({i}/{files_to_download})...")
                file_size = 0
                file_size_mb = 0
                try:
                    # Get file size for progress
                    file_size = ftp.size(sdf_file)
                    if file_size:
                        file_size_mb = file_size / (1024 * 1024)
                        print(f"   📦 File size: {file_size_mb:.1f} MB")
                        print(f"   📊 Starting download... (this may take several minutes)")
                except:
                    pass
                
                if download_sdf_file(ftp, sdf_file, local_gz):
                    print(f"   ✅ Download complete")
                    
                    # Decompress with progress and error handling
                    print(f"   📦 Decompressing {file_size_mb:.1f} MB file...")
                    decompressed_size = 0
                    try:
                        with gzip.open(local_gz, 'rb') as f_in:
                            with open(local_sdf, 'wb') as f_out:
                                while True:
                                    chunk = f_in.read(1024 * 1024)  # Read 1MB at a time
                                    if not chunk:
                                        break
                                    f_out.write(chunk)
                                    decompressed_size += len(chunk)
                                    if decompressed_size % (10 * 1024 * 1024) == 0:  # Every 10MB
                                        print(f"      Decompressed: {decompressed_size / (1024*1024):.1f} MB...", end='\r')
                        print()  # New line
                        print(f"   ✅ Decompressed ({decompressed_size / (1024*1024):.1f} MB)")
                    except Exception as decomp_error:
                        print(f"\n   ❌ Decompression error: {decomp_error}")
                        print(f"   ⚠️  The downloaded file may be corrupted or incomplete")
                        print(f"   🔄 Attempting to re-download the file...")
                        # Delete corrupted files
                        local_gz.unlink(missing_ok=True)
                        local_sdf.unlink(missing_ok=True)
                        # Retry download
                        if download_sdf_file(ftp, sdf_file, local_gz, max_retries=1):
                            # Try decompression again
                            try:
                                with gzip.open(local_gz, 'rb') as f_in:
                                    with open(local_sdf, 'wb') as f_out:
                                        shutil.copyfileobj(f_in, f_out)
                                print(f"   ✅ Decompressed successfully on retry")
                            except Exception as retry_error:
                                print(f"   ❌ Decompression failed again: {retry_error}")
                                print(f"   ⚠️  Skipping this file and trying next one...")
                                continue
                        else:
                            print(f"   ❌ Re-download failed, skipping this file...")
                            continue
                    
                    # Convert to SMILES
                    print(f"   🔄 Converting SDF to SMILES...")
                    if download_full_files or not max_molecules:
                        # Import all molecules from the file
                        file_molecules = sdf_to_smiles(local_sdf, max_molecules=None)
                    else:
                        # Limit to remaining molecules needed
                        remaining = max_molecules - len(molecules)
                        file_molecules = sdf_to_smiles(local_sdf, remaining)
                    molecules.extend(file_molecules)
                    print(f"   ✅ Extracted {len(file_molecules)} valid molecules from this file")
                    
                    # Clean up
                    local_gz.unlink()
                    local_sdf.unlink()
                    
                    print(f"   📊 Total molecules so far: {len(molecules)}/{max_molecules}")
                else:
                    print(f"   ⚠️  Failed to download {sdf_file}, trying next file...")
            
            # Write to output file
            if molecules:
                if max_molecules:
                    final_count = min(len(molecules), max_molecules)
                    molecules_to_write = molecules[:max_molecules]
                else:
                    final_count = len(molecules)
                    molecules_to_write = molecules
                
                print(f"\n💾 Writing {final_count} molecules to {output_file}...")
                with open(output_file, 'w') as f:
                    for mol in molecules_to_write:
                        # Format: ID\tSMILES\tMW\tNAME\tFORMULA\tINCHI\tINCHIKEY\tCID
                        name = mol.get('name', '')
                        formula = mol.get('formula', '')
                        inchi = mol.get('inchi', '')
                        inchikey = mol.get('inchikey', '')
                        cid = mol.get('pubchem_cid', '')
                        f.write(f"{mol['id']}\t{mol['smiles']}\t{mol['molecular_weight']:.2f}\t{name}\t{formula}\t{inchi}\t{inchikey}\t{cid}\n")
                
                print(f"✅ Success! Created {output_file}")
                print(f"   Total molecules: {final_count}")
                print("=" * 60)
                return True
            else:
                print("❌ No molecules extracted from downloaded files")
                return False
        
        finally:
            # Clean up temp directory
            print(f"\n🧹 Cleaning up temporary files...")
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("✅ Cleanup complete")
    
    except Exception as e:
        print(f"\n❌ Error during FTP download: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        print(f"\n🔌 Disconnecting from FTP...")
        try:
            ftp.quit()
            print("✅ Disconnected")
        except:
            pass

def download_compound_list(list_id: str, max_molecules: int = 10000, output_file: Path = None):
    """
    Download a specific PubChem compound list.
    
    Args:
        list_id: PubChem compound list ID
        max_molecules: Maximum number of molecules
        output_file: Output file path
    """
    print(f"📥 Downloading PubChem compound list: {list_id}")
    print("   Note: This feature requires PubChem list ID")
    print("   For now, use the general compound download")
    # TODO: Implement compound list download
    return False

def main():
    parser = argparse.ArgumentParser(
        description="Download PubChem compounds via FTP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download 10,000 compounds
  python download_pubchem_ftp.py --max-molecules 10000

  # Specify output file
  python download_pubchem_ftp.py --max-molecules 10000 --output data/downloads/pubchem.smi

Note: PubChem FTP contains millions of compounds. The script downloads a subset
of SDF files and converts them to SMILES format.
        """
    )
    
    parser.add_argument(
        "--max-molecules",
        type=int,
        default=None,
        help="Maximum number of molecules to download (default: None = all from downloaded files)"
    )
    
    parser.add_argument(
        "--full-file",
        action='store_true',
        help="Download complete SDF files and import all molecules (ignores --max-molecules)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/downloads/pubchem_compounds.smi"),
        help="Output SMILES file path (default: data/downloads/pubchem_compounds.smi)"
    )
    parser.add_argument(
        "--compound-list",
        type=str,
        default=None,
        help="PubChem compound list ID (not yet implemented)"
    )
    
    args = parser.parse_args()
    
    if not RDKIT_AVAILABLE:
        print("❌ Error: RDKit is required for SDF to SMILES conversion")
        print("   Install with: pip install rdkit")
        print("   Or use conda: conda install -c conda-forge rdkit")
        sys.exit(1)
    
    print("🚀 PubChem FTP Downloader")
    print("=" * 60)
    print(f"Max molecules: {args.max_molecules}")
    print(f"Output file: {args.output}")
    print("=" * 60)
    
    if args.compound_list:
        success = download_compound_list(args.compound_list, args.max_molecules, args.output)
    else:
        success = download_pubchem_compounds(args.max_molecules, args.output, download_full_files=args.full_file)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

