# BioNeighbor
BioNeighbor: A molecular similarity engine inspired by collaborative filtering — find “neighbor” molecules to existing drugs and bioactive compounds.

**Discover structurally and functionally similar molecules to explore biochemical pathways and improve drug efficacy.**

---

## Overview

BioNeighbor is a molecular similarity and discovery platform inspired by **collaborative filtering (CF)**. Its goal is to help researchers, software engineers, and drug discovery enthusiasts explore “neighbor” molecules — compounds structurally or biologically similar to a molecule of interest.  

The system is designed to be **offline-friendly**, running entirely on a user’s Mac (or other desktop platform) without requiring a server. Users can pick an existing drug or bioactive compound and find similar molecules that might improve efficacy, target specific pathways, or serve as candidate inhibitors.  

BioNeighbor combines:
- Public biochemical datasets (ChEMBL, BindingDB)  
- Molecular fingerprints and embeddings (computed via RDKit or other cheminformatics tools)  
- Nearest-neighbor and similarity search engines (FAISS / vector search)  
- Optional collaborative filtering for hybrid recommendation of molecules  

---

## Key Features

- **Molecule-centric search:** Start with a known drug or bioactive compound and find similar molecules.  
- **Biological target awareness:** Incorporates pathway and protein target information (e.g., adenosine-related targets) when available.  
- **Offline operation:** No server required — the Python engine for molecular similarity runs locally, called from a Mac app or other front-end.  
- **Interactive visualization:** Molecule structures can be visualized in 2D or 3D using embedded viewers (e.g., 3Dmol.js, NGL Viewer, or SwiftUI wrapper).  
- **CF-inspired neighbor recommendations:** Uses the concept of collaborative filtering applied to molecules and their activity profiles to prioritize promising candidates.  

---

## Use Cases

- **Drug repurposing:** Discover alternative molecules similar to existing drugs to target new pathways.  
- **Adenosine pathway research:** Explore candidates that modulate adenosine production (e.g., CD73, CD39, A2A receptor inhibitors).  
- **Molecular discovery for other pathways:** Flexible framework supports any pathway or target with available activity data.  
- **Educational / research tool:** Provides an approachable interface for exploring chemical space and molecular similarity without needing deep ML expertise.  

---

## Architecture

BioNeighbor separates **frontend** and **backend logic** while remaining fully offline:

1. **Frontend:** Kotlin Multiplatform (KMP) application (Mac, Windows, or Web).  
   - Allows users to input/select molecules and view similarity results.  
   - Visualizes molecules using embedded 2D/3D viewers.  

2. **Backend / local engine:** Python script with:  
   - RDKit for fingerprint and descriptor computation  
   - FAISS (or Milvus) for nearest-neighbor vector search  
   - Optional collaborative filtering model (from stanscofi/benchscofi)  
   - Precomputed embeddings or similarity matrices shipped with the app  

The frontend communicates with the local Python engine via:  
- Process calls (`Process` in Swift/KMP) or  
- PythonKit integration  

---

## Datasets

BioNeighbor supports multiple data sources with automatic fallback:

1. **ZINC Database** (Primary - Recommended)
   - Curated drug-like and lead-like subsets
   - Bulk SMILES file downloads (no API rate limits)
   - Reliable, free, and designed for virtual screening
   - URL: https://zinc.docking.org/
   - Automatically downloads and caches locally

2. **PubChem** (Fallback)
   - Bulk downloads via FTP or API
   - Large database of chemical compounds
   - Rate-limited API, but provides bulk download options

3. **ChEMBL** (Legacy - Often Unavailable)
   - Note: ChEMBL API has been down for 2+ years (see [issue #134](https://github.com/chembl/chembl_webresource_client/issues/134))
   - Will be tried but typically fails

4. **Sample Data** (Last Resort)
   - Built-in curated list of 35+ FDA-approved drugs
   - Can generate variations for testing
   - Works offline, no internet required

**Data Download Priority:**
1. ZINC database (drug-like subset) - **Recommended for 10,000+ molecules**
2. PubChem bulk download
3. ChEMBL API (if available)
4. PubChem API (rate-limited)
5. Sample data (for testing)

Users can also extend the datasets with custom molecules or manually download ZINC files.

---

## CF Metaphor

BioNeighbor leverages a **collaborative filtering metaphor**:

- Molecules = “items”  
- Targets / pathways = “users”  
- Activity / binding data = “ratings”  

This analogy allows CF-inspired models to prioritize molecules based on structural similarity **and** shared biological activity.

---

## Getting Started

### Prerequisites

- **macOS** 13.0 or later
- **Python 3.9+** (Python 3.11 or 3.12 recommended)
  - Install via Homebrew: `brew install python3` or `brew install python@3.12`
  - Or use conda: `conda install python=3.11`
- **Xcode 14+** (for macOS app development)
- **Internet connection** (for initial dataset download)

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd bio-neighbor
   ```

2. **Run the setup script:**
   ```bash
   ./setup.sh
   ```
   This will:
   - Create a Python virtual environment
   - Install all Python dependencies (RDKit, FAISS, etc.)
   - Create necessary directories
   
   **Note:** If RDKit installation fails via pip, you can use conda:
   ```bash
   conda install -c conda-forge rdkit
   ```
   Or see [INSTALL_RDKIT.md](INSTALL_RDKIT.md) for alternative installation methods.

3. **Run the setup script:**
   ```bash
   ./setup.sh
   ```
   This will:
   - Create a Python virtual environment (if not using conda)
   - Install remaining Python dependencies (FAISS, etc.)
   - Create necessary directories

3. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate
   ```

4. **Set up the data and build the search index:**
   ```bash
   python backend/main.py setup --max-molecules 10000
   ```
   This will:
   - **Automatically download from ZINC database** (recommended - no API limits)
   - Falls back to PubChem, ChEMBL, or sample data if needed
   - Compute molecular fingerprints using RDKit
   - Build the FAISS similarity search index
   
   **Note:** For 10,000+ molecules, ZINC database is recommended. If automatic download fails, see [DOWNLOAD_DATA.md](DOWNLOAD_DATA.md) for manual download instructions.

5. **Test the backend (optional):**
   ```bash
   # Search for molecules similar to aspirin
   python backend/main.py search "CC(=O)Oc1ccccc1C(=O)O" --top-k 5
   
   # Start the API server
   python backend/api.py --mode http
   ```

6. **Build and run the macOS app:**
   - Open Xcode
   - Create a new macOS App project in `macos_app/` directory
   - Add all Swift files from `macos_app/BioNeighbor/`
   - Build and run (⌘R)
   - The app will automatically start the backend if needed

### Backend API

The backend provides a REST API on `http://127.0.0.1:5000`:

- `GET /health` - Health check
- `POST /search` - Search by SMILES string
- `POST /search/chembl` - Search by ChEMBL ID
- `GET /molecule/<index>` - Get molecule by index
- `POST /render` - Render molecule structure image

### Command Line Interface

The backend also provides a CLI for testing:

```bash
# Setup data and index
python backend/main.py setup --max-molecules 10000

# Search by SMILES
python backend/main.py search "CC(=O)Oc1ccccc1C(=O)O" --top-k 10

# Search by ChEMBL ID
python backend/main.py search-chembl CHEMBL25 --top-k 5
```

### Project Structure

```
bio-neighbor/
├── backend/              # Python backend
│   ├── data_loader.py    # ChEMBL dataset loading
│   ├── fingerprints.py   # Molecular fingerprint computation
│   ├── index_builder.py # FAISS index building
│   ├── search_engine.py  # Similarity search engine
│   ├── api.py           # HTTP API server
│   ├── molecule_renderer.py # 2D structure rendering
│   └── main.py          # CLI entry point
├── macos_app/           # SwiftUI macOS app
│   └── BioNeighbor/     # Swift source files
├── data/                # Data files (datasets, indices)
├── venv/                # Python virtual environment
└── setup.sh             # Setup script
```

---

## Naming

The project name **BioNeighbor** reflects its CF-inspired approach:  
> “Find the biological neighbors of a molecule in chemical and activity space.”

---

## Future Work

- Integration of additional datasets (ZINC, FDA-approved drugs).  
- Optional training of collaborative filtering models locally.  
- Improved offline performance with optimized vector search indices.  
- Enhanced visualization of molecular clusters and pathways.  

---

## License

- Core code: MIT
- Datasets: Check individual dataset licenses (ChEMBL, BindingDB, PubChem).