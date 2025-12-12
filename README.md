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

Initial datasets include publicly available sources:

- **ChEMBL:** Approved drugs, small molecules, activity data, and targets.  
- **BindingDB:** Molecule × protein binding affinities for constructing similarity/recommendation matrices.  
- **PubChem Bioassays:** Optional for expanded molecular sets.  

Users can also extend the datasets with custom molecules or assay results.

---

## CF Metaphor

BioNeighbor leverages a **collaborative filtering metaphor**:

- Molecules = “items”  
- Targets / pathways = “users”  
- Activity / binding data = “ratings”  

This analogy allows CF-inspired models to prioritize molecules based on structural similarity **and** shared biological activity.

---

## Getting Started (Research / Prototype Mode)

1. Install Python dependencies: RDKit, FAISS, stanscofi/benchscofi.  
2. Load precomputed embeddings or compute fingerprints for molecules.  
3. Run the local Python engine to query nearest-neighbor molecules.  
4. Launch KMP frontend to select a molecule and visualize results.  

> A full Mac app prototype can be built with Kotlin Multiplatform + SwiftUI/JavaScript visualization, calling the local Python engine for similarity computation.

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