#!/usr/bin/env python3
"""
Helper script to manually download ZINC database files.
If automatic download fails, use this script with a direct download URL.

ZINC22 uses rsync for bulk downloads. See:
https://wiki.docking.org/index.php/ZINC22:Downloading

For rsync downloads, use:
    rsync -L -a --progress rsync://files.docking.org/ZINC22-3D/<tranche>/*.smi.gz <output_dir>

For HTTP downloads (if available):
    python download_zinc_manual.py <url> <output_file>
    
Example (HTTP):
    python download_zinc_manual.py https://zinc.docking.org/substances/subsets/drug-like.smi data/downloads/zinc_drug-like.smi

Example (rsync - run in terminal):
    rsync -L -a --progress rsync://files.docking.org/ZINC22-3D/H06/*.smi.gz data/downloads/
    cd data/downloads && gunzip *.smi.gz
"""

import sys
import requests
from pathlib import Path

def download_file(url: str, output_path: Path):
    """Download a file from URL to local path."""
    print(f"⬇️  Downloading from: {url}")
    print(f"📁 Saving to: {output_path}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and downloaded % (10 * 1024 * 1024) == 0:
                        progress = (downloaded / total_size) * 100
                        print(f"   Progress: {progress:.1f}% ({downloaded / 1024 / 1024:.1f} MB)")
        
        print(f"✅ Downloaded {output_path.name} ({downloaded / 1024 / 1024:.1f} MB)")
        print(f"\nYou can now run:")
        print(f"  python backend/main.py setup --max-molecules 10000")
        print(f"\nThe system will use the cached file at: {output_path}")
    
    except Exception as e:
        print(f"❌ Error downloading: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python download_zinc_manual.py <url> <output_file>")
        print("\nExample:")
        print("  python download_zinc_manual.py https://zinc.docking.org/substances/subsets/drug-like.smi data/downloads/zinc_drug-like.smi")
        print("\nTo find ZINC download URLs:")
        print("  1. Visit https://zinc.docking.org/browse/subsets/")
        print("  2. Click on a subset (e.g., 'drug-like')")
        print("  3. Look for download links or 'Export' options")
        print("  4. Copy the direct download URL")
        sys.exit(1)
    
    url = sys.argv[1]
    output_path = Path(sys.argv[2])
    
    download_file(url, output_path)

