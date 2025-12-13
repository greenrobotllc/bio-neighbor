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
from typing import List, Optional

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# PubChem FTP configuration
PUBCHEM_FTP_HOST = "ftp.ncbi.nlm.nih.gov"
PUBCHEM_FTP_BASE = "/pubchem/Compound/CURRENT-Full/SDF"
PUBCHEM_COMPOUND_LISTS = "/pubchem/Compound/Monthly/YYYY-MM-01/Compound_000500001_000525000.sdf.gz"

def download_sdf_file(ftp: ftplib.FTP, remote_path: str, local_path: Path):
    """Download a single SDF file from PubChem FTP."""
    print(f"   Downloading: {remote_path}")
    
    try:
        with open(local_path, 'wb') as f:
            ftp.retrbinary(f'RETR {remote_path}', f.write)
        print(f"   ✅ Downloaded {local_path.name}")
        return True
    except Exception as e:
        print(f"   ❌ Error downloading {remote_path}: {e}")
        return False

def sdf_to_smiles(sdf_path: Path, max_molecules: Optional[int] = None) -> List[dict]:
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
        
        for i, mol in enumerate(supplier):
            if max_molecules and len(molecules) >= max_molecules:
                break
            
            if mol is None:
                continue
            
            try:
                # Get SMILES
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
                
                molecules.append({
                    'id': cid or f"PUBCHEM_{i}",
                    'smiles': smiles,
                    'molecular_weight': mw
                })
                
                if len(molecules) % 100 == 0:
                    print(f"     ✓ Extracted {len(molecules)} molecules...")
            
            except Exception:
                continue
        
        print(f"   ✅ Extracted {len(molecules)} valid molecules")
        return molecules
    
    except Exception as e:
        print(f"   ❌ Error converting SDF: {e}")
        return []

def download_pubchem_compounds(max_molecules: int = 10000, output_file: Path = None):
    """
    Download PubChem compounds via FTP and convert to SMILES.
    
    Args:
        max_molecules: Maximum number of molecules to download
        output_file: Output SMILES file path
    """
    print("📥 Connecting to PubChem FTP server...")
    print(f"   Host: {PUBCHEM_FTP_HOST}")
    print(f"   Path: {PUBCHEM_FTP_BASE}")
    
    if output_file is None:
        output_file = Path("data/downloads/pubchem_compounds.smi")
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to FTP
    try:
        ftp = ftplib.FTP(PUBCHEM_FTP_HOST)
        ftp.login()  # Anonymous login
        print("✅ Connected to PubChem FTP")
    except Exception as e:
        print(f"❌ Error connecting to FTP: {e}")
        return False
    
    try:
        # Change to compound directory
        ftp.cwd(PUBCHEM_FTP_BASE)
        
        # List available files
        print("\n📋 Listing available compound files...")
        files = []
        ftp.retrlines('LIST', files.append)
        
        # Filter for SDF files
        sdf_files = [f.split()[-1] for f in files if f.endswith('.sdf.gz')]
        
        if not sdf_files:
            print("❌ No SDF files found")
            return False
        
        print(f"   Found {len(sdf_files)} SDF files")
        print(f"   (PubChem has millions of compounds - we'll download a subset)")
        
        # Download first few files to get enough molecules
        # Each file typically contains thousands of compounds
        molecules = []
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            files_to_download = min(5, len(sdf_files))  # Download first 5 files
            print(f"\n⬇️  Downloading {files_to_download} SDF files...")
            
            for i, sdf_file in enumerate(sdf_files[:files_to_download]):
                if len(molecules) >= max_molecules:
                    break
                
                local_gz = temp_dir / sdf_file
                local_sdf = temp_dir / sdf_file.replace('.gz', '')
                
                # Download
                if download_sdf_file(ftp, sdf_file, local_gz):
                    # Decompress
                    print(f"   Decompressing {sdf_file}...")
                    with gzip.open(local_gz, 'rb') as f_in:
                        with open(local_sdf, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    
                    # Convert to SMILES
                    file_molecules = sdf_to_smiles(local_sdf, max_molecules - len(molecules))
                    molecules.extend(file_molecules)
                    
                    # Clean up
                    local_gz.unlink()
                    local_sdf.unlink()
                    
                    print(f"   Total molecules so far: {len(molecules)}")
            
            # Write to output file
            if molecules:
                print(f"\n💾 Writing {len(molecules)} molecules to {output_file}...")
                with open(output_file, 'w') as f:
                    for mol in molecules[:max_molecules]:
                        f.write(f"{mol['id']}\t{mol['smiles']}\t{mol['molecular_weight']:.2f}\n")
                
                print(f"✅ Success! Created {output_file} with {len(molecules)} molecules")
                print(f"\nYou can now run:")
                print(f"  python backend/main.py setup --max-molecules {len(molecules)}")
                return True
            else:
                print("❌ No molecules extracted")
                return False
        
        finally:
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    finally:
        ftp.quit()

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
        default=10000,
        help="Maximum number of molecules to download (default: 10000)"
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
        success = download_pubchem_compounds(args.max_molecules, args.output)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

