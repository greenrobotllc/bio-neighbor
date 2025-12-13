#!/usr/bin/env python3
"""
Download ZINC22 molecules using rsync.
ZINC22 uses rsync for bulk downloads (see https://wiki.docking.org/index.php/ZINC22:Downloading)

Usage:
    python download_zinc_rsync.py [--tranche H06] [--max-molecules 10000] [--output-dir data/downloads]

Examples:
    # Download H06 tranche (recommended for drug-like molecules)
    python download_zinc_rsync.py --tranche H06

    # Download multiple tranches to get more molecules
    python download_zinc_rsync.py --tranche H06 --tranche H07 --tranche H08

    # Download and automatically sample to get exactly 10,000 molecules
    python download_zinc_rsync.py --tranche H06 --max-molecules 10000
"""

import subprocess
import sys
import argparse
from pathlib import Path
from typing import Optional
import gzip
import shutil

# ZINC22 rsync configuration
# Try multiple possible paths - ZINC22 structure may vary
ZINC_RSYNC_BASES = [
    "rsync://files.docking.org/ZINC22-3D",
    "rsync://files.docking.org/ZINC22",
]
# Common tranches that contain drug-like molecules
COMMON_TRANCHES = ["H06", "H07", "H08", "H09", "H10"]

def check_rsync_available():
    """Check if rsync is installed."""
    try:
        result = subprocess.run(["rsync", "--version"], 
                               capture_output=True, 
                               text=True, 
                               timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def download_tranche(tranche: str, output_dir: Path, max_files: Optional[int] = None):
    """
    Download a ZINC22 tranche using rsync.
    
    Args:
        tranche: Tranche name (e.g., "H06")
        output_dir: Directory to save files
        max_files: Maximum number of files to download (None = all)
        
    Returns:
        List of downloaded .smi.gz file paths
    """
    print(f"📥 Downloading ZINC22 tranche: {tranche}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Try different rsync base paths
    for rsync_base in ZINC_RSYNC_BASES:
        rsync_url = f"{rsync_base}/{tranche}/"
        print(f"   Trying: {rsync_url}")
        print(f"   Destination: {output_dir}/")
    
        rsync_cmd = [
            "rsync",
            "-L",  # Copy symlinks as files
            "-a",  # Archive mode
            "--progress",  # Show progress
            "--prune-empty-dirs",  # Don't create empty dirs
            "--include=*.smi.gz",  # Only download .smi.gz files
            "--exclude=*",  # Exclude everything else
            "--timeout=30",  # 30 second timeout per operation
            rsync_url,
            str(output_dir) + "/"
        ]
        
        print(f"   Running: {' '.join(rsync_cmd)}")
        print(f"   This may take a while (tranches can be large)...")
        
        try:
            # Run rsync with timeout
            process = subprocess.Popen(
                rsync_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Print output in real-time
            for line in process.stdout:
                print(f"   {line.rstrip()}")
            
            process.wait(timeout=300)  # 5 minute overall timeout
            
            if process.returncode == 0:
                # Find downloaded files
                downloaded_files = list(output_dir.glob(f"{tranche}/*.smi.gz"))
                if not downloaded_files:
                    # Try without tranche subdirectory
                    downloaded_files = list(output_dir.glob("*.smi.gz"))
                
                # Apply max_files limit if specified
                if max_files is not None and len(downloaded_files) > max_files:
                    downloaded_files = downloaded_files[:max_files]
                    print(f"   ⚠️  Limited to {max_files} files (max_files specified)")
                
                if downloaded_files:
                    print(f"✅ Downloaded {len(downloaded_files)} files from tranche {tranche}")
                    return downloaded_files
            
            # If we get here, this base path didn't work, try next
            print(f"   ⚠️  Path {rsync_base} didn't work, trying next...")
            continue
        
        except subprocess.TimeoutExpired:
            print(f"   ⚠️  Timeout connecting to {rsync_base}, trying next path...")
            if 'process' in locals():
                process.kill()
            continue
        except Exception as e:
            print(f"   ⚠️  Error with {rsync_base}: {e}, trying next...")
            continue
    
    # If all paths failed
    print(f"\n❌ Could not connect to ZINC22 rsync server")
    print(f"   Tried: {', '.join(ZINC_RSYNC_BASES)}")
    print(f"\n   Possible issues:")
    print(f"   1. Server may be down or slow")
    print(f"   2. Network/firewall blocking rsync (port 873)")
    print(f"   3. Server structure may have changed")
    print(f"\n   Alternatives:")
    print(f"   1. Try again later - rsync servers can be intermittent")
    print(f"   2. Use the enhanced sample data generator:")
    print(f"      python backend/main.py setup --max-molecules 10000 --force")
    print(f"   3. Check ZINC website for alternative download methods:")
    print(f"      https://zinc.docking.org/")
    print(f"      https://wiki.docking.org/index.php/ZINC22:Downloading")
    return []

def decompress_files(gz_files: list, output_dir: Path, keep_gz: bool = False):
    """
    Decompress .smi.gz files to .smi files.
    
    Args:
        gz_files: List of .smi.gz file paths
        output_dir: Directory containing the files
        
    Returns:
        List of decompressed .smi file paths
    """
    print(f"\n📦 Decompressing {len(gz_files)} files...")
    
    smi_files = []
    for gz_file in gz_files:
        try:
            smi_file = gz_file.with_suffix('')  # Remove .gz extension
            
            with gzip.open(gz_file, 'rb') as f_in:
                with open(smi_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            smi_files.append(smi_file)
            
            # Remove .gz file to save space unless keep_gz is True
            if not keep_gz:
                try:
                    gz_file.unlink()
                except Exception as e:
                    print(f"   ⚠️  Could not remove {gz_file.name}: {e}")
            
            if len(smi_files) % 10 == 0:
                print(f"   ✓ Decompressed {len(smi_files)}/{len(gz_files)} files...")
        
        except Exception as e:
            print(f"   ⚠️  Error decompressing {gz_file.name}: {e}")
            continue
    
    print(f"✅ Decompressed {len(smi_files)} files")
    return smi_files

def combine_smi_files(smi_files: list, output_file: Path, max_molecules: int = None):
    """
    Combine multiple .smi files into one, optionally sampling.
    
    Args:
        smi_files: List of .smi file paths
        output_file: Output combined file path
        max_molecules: Maximum number of molecules to include (None = all)
    """
    print(f"\n🔗 Combining {len(smi_files)} SMILES files...")
    
    total_lines = 0
    molecules_written = 0
    
    with open(output_file, 'w') as out_f:
        for smi_file in smi_files:
            if max_molecules and molecules_written >= max_molecules:
                break
            
            try:
                with open(smi_file, 'r') as in_f:
                    for line in in_f:
                        if max_molecules and molecules_written >= max_molecules:
                            break
                        
                        line = line.strip()
                        if line and not line.startswith('#'):
                            out_f.write(line + '\n')
                            molecules_written += 1
                            total_lines += 1
                            
                            if total_lines % 10000 == 0:
                                print(f"   ✓ Processed {total_lines} molecules...")
            
            except Exception as e:
                print(f"   ⚠️  Error reading {smi_file.name}: {e}")
                continue
    
    print(f"✅ Combined {molecules_written} molecules into {output_file.name}")
    return molecules_written

def main():
    parser = argparse.ArgumentParser(
        description="Download ZINC22 molecules using rsync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download H06 tranche
  python download_zinc_rsync.py --tranche H06

  # Download multiple tranches
  python download_zinc_rsync.py --tranche H06 --tranche H07

  # Download and combine to get exactly 10,000 molecules
  python download_zinc_rsync.py --tranche H06 --max-molecules 10000 --output data/downloads/zinc_drug-like.smi
        """
    )
    
    parser.add_argument(
        "--tranche",
        action="append",
        default=[],
        help="Tranche(s) to download (e.g., H06). Can specify multiple times. Default: H06"
    )
    parser.add_argument(
        "--max-molecules",
        type=int,
        default=None,
        help="Maximum number of molecules to include in combined file"
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Maximum number of .smi.gz files to download per tranche"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/downloads/zinc_combined.smi"),
        help="Output file path for combined SMILES (default: data/downloads/zinc_combined.smi)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/downloads"),
        help="Directory to download files (default: data/downloads)"
    )
    parser.add_argument(
        "--keep-gz",
        action="store_true",
        help="Keep .smi.gz files after decompression (default: delete to save space)"
    )
    
    args = parser.parse_args()
    
    # Check rsync availability
    if not check_rsync_available():
        print("❌ Error: rsync is not installed or not in PATH")
        print("\nInstall rsync:")
        print("  macOS: brew install rsync")
        print("  Linux: sudo apt-get install rsync")
        print("  Or use your system's package manager")
        sys.exit(1)
    
    # Default to H06 if no tranche specified
    tranches = args.tranche if args.tranche else ["H06"]
    
    print("🚀 ZINC22 Rsync Downloader")
    print("=" * 60)
    print(f"Tranches to download: {', '.join(tranches)}")
    print(f"Output directory: {args.output_dir}")
    if args.max_molecules:
        print(f"Max molecules: {args.max_molecules}")
    print("=" * 60)
    
    # Download each tranche
    all_gz_files = []
    for tranche in tranches:
        gz_files = download_tranche(tranche, args.output_dir, max_files=args.max_files)
        all_gz_files.extend(gz_files)
    
    if not all_gz_files:
        print("\n❌ No files downloaded. Check your internet connection and rsync setup.")
        sys.exit(1)
    
    # Decompress files
    smi_files = decompress_files(all_gz_files, args.output_dir, keep_gz=args.keep_gz)
    
    if not smi_files:
        print("\n❌ No files decompressed.")
        sys.exit(1)
    
    # Combine files if output specified
    if args.output:
        molecules = combine_smi_files(smi_files, args.output, args.max_molecules)
        print(f"\n✅ Success! Created {args.output} with {molecules} molecules")
        print(f"\nYou can now run:")
        print(f"  python backend/main.py setup --max-molecules {molecules or args.max_molecules or 10000}")
        print(f"\nThe system will automatically use: {args.output}")
    else:
        print(f"\n✅ Success! Downloaded and decompressed {len(smi_files)} files")
        print(f"Files are in: {args.output_dir}")
        print(f"\nThe system will automatically detect .smi files in the downloads directory")

if __name__ == "__main__":
    main()

