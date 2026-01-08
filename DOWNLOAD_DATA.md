# Downloading Molecular Data for BioNeighbor

This guide explains how to get 10,000+ real molecules for BioNeighbor without relying on APIs.

## Automatic Download (Recommended)

The system will automatically try to download from multiple sources:

```bash
python backend/main.py setup --max-molecules 10000 --force
```

**Priority Order:**
1. **ZINC Database** - Tries to download drug-like subset automatically
2. **PubChem Bulk** - Falls back to PubChem if ZINC fails
3. **ChEMBL** - Tries ChEMBL (often unavailable)
4. **PubChem API** - Rate-limited API as backup
5. **Sample Data** - Built-in molecules for testing

## Manual ZINC Download

ZINC22 uses **rsync** for downloads, not direct HTTP URLs. See the [official ZINC22 downloading guide](https://wiki.docking.org/index.php/ZINC22:Downloading).

### Method 1: Using the rsync download script (Easiest)

We provide a Python script that handles rsync downloads automatically:

```bash
# Download H06 tranche (recommended for drug-like molecules)
python backend/download_zinc_rsync.py --tranche H06

# Download multiple tranches to get more molecules
python backend/download_zinc_rsync.py --tranche H06 --tranche H07 --tranche H08

# Download and automatically combine to get exactly 10,000 molecules
python backend/download_zinc_rsync.py --tranche H06 --max-molecules 10000 --output data/downloads/zinc_drug-like.smi
```

The script will:
- Check if rsync is installed
- Download the specified tranche(s)
- Decompress .smi.gz files automatically
- Optionally combine files and sample to get exactly the number you need

### Method 2: Using rsync directly (Manual)

ZINC22 is organized by tranches (H00, H01, H02, etc.). To download drug-like molecules:

```bash
# Create downloads directory
mkdir -p data/downloads

# Download a tranche (example: H06)
# ZINC22 files are compressed (.smi.gz)
rsync -L -a --progress \
  rsync://files.docking.org/ZINC22-3D/H06/*.smi.gz \
  data/downloads/

# Unzip the files
cd data/downloads
gunzip *.smi.gz

# Combine or use individual files
# The system will automatically detect .smi files in the downloads directory
```

**Note:** You may need to download multiple tranches to get 10,000+ molecules. Each tranche contains thousands of molecules.

### Method 3: Using HTTP (if available)

Some ZINC subsets may be available via HTTP:

1. Visit https://zinc.docking.org/browse/subsets/
2. Click on "drug-like" or "lead-like" subset
3. Look for download/export options
4. Copy the direct download URL
5. Use the helper script:

```bash
python backend/download_zinc_manual.py <ZINC_URL> data/downloads/zinc_drug-like.smi
```

### Step 3: Run Setup

The system will automatically detect and use downloaded files:

```bash
python backend/main.py setup --max-molecules 10000
```

## Alternative: Use PubChem FTP

PubChem provides bulk downloads via FTP:

1. Connect to: `ftp.ncbi.nlm.nih.gov/pubchem/Compound/CURRENT-Full/SDF/`
2. Download compound files (SDF format)
3. Convert to SMILES using RDKit
4. Place in `data/downloads/` directory

### PubChem Download Sizes

**File Size Information:**
- Each PubChem SDF file is typically **300-500 MB** (compressed)
- Each file contains approximately **500,000 compounds**
- Files are compressed in `.sdf.gz` format

**Estimated Download Sizes:**
- **10,000 molecules**: ~300-500 MB (1 file)
- **50,000 molecules**: ~600 MB - 1 GB (2 files)
- **100,000+ molecules**: Multiple GB (multiple files)

**Disk Space Recommendations:**
- Ensure you have at least **2-3 GB free space** for downloads and processing
- Temporary files during conversion may require additional space
- Processed SMILES files are much smaller (~10-50 MB for 10,000 molecules)

**Note:** The system will automatically download files incrementally until it reaches your target molecule count. You can stop the download at any time and use the molecules already downloaded.

## Expected Results

- **ZINC download**: Should get 10,000+ molecules in 5-10 minutes
- **File size**: ZINC drug-like subset is typically 100-500 MB
- **Molecules**: All validated with RDKit, filtered for drug-like properties (MW 150-800)

## Troubleshooting

**ZINC download fails:**
- URLs may have changed - check https://zinc.docking.org/browse/subsets/
- Use manual download script (see above)
- System will automatically fall back to other sources

**Need more molecules:**
- ZINC can provide 100K+ molecules easily
- Just increase `--max-molecules` parameter
- System will sample from the downloaded file

**Offline usage:**
- Once downloaded, files are cached in `data/downloads/`
- Subsequent runs use cached files (valid for 7 days)
- Can work completely offline after initial download

