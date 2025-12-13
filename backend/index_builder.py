"""
FAISS index builder for molecular similarity search.
Builds and saves FAISS indices from molecular fingerprints.
"""

import numpy as np
import faiss
from pathlib import Path
from typing import Tuple, Optional
import pickle

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
INDEX_PATH = DATA_DIR / "faiss_index.bin"
METADATA_PATH = DATA_DIR / "index_metadata.pkl"


def build_faiss_index(fingerprints: np.ndarray, index_type: str = "L2") -> faiss.Index:
    """
    Build a FAISS index from fingerprint matrix.
    
    Args:
        fingerprints: Fingerprint matrix (n_molecules, n_bits) as float32
        index_type: Type of index - "L2" (Euclidean) or "cosine" (cosine similarity)
        
    Returns:
        FAISS index object
    """
    print(f"🔨 Building FAISS index ({index_type}) for {len(fingerprints)} fingerprints...")
    
    # Ensure fingerprints are float32 and contiguous
    fingerprints = np.ascontiguousarray(fingerprints.astype(np.float32))
    dimension = fingerprints.shape[1]
    
    if index_type == "L2":
        # L2 (Euclidean) distance index
        # Use IndexFlatL2 for exact search (fast for < 1M vectors)
        index = faiss.IndexFlatL2(dimension)
    elif index_type == "cosine":
        # Cosine similarity: normalize vectors and use L2 index
        # Normalize fingerprints to unit length (avoid mutating original)
        fingerprints = fingerprints.copy()
        faiss.normalize_L2(fingerprints)
        index = faiss.IndexFlatL2(dimension)
    else:
        raise ValueError(f"Unknown index type: {index_type}. Use 'L2' or 'cosine'")
    
    # Add fingerprints to index
    print("  Adding fingerprints to index...")
    index.add(fingerprints)
    
    print(f"✅ Built index with {index.ntotal} vectors")
    return index


def save_index(index: faiss.Index, metadata: dict, index_path: Path = INDEX_PATH, metadata_path: Path = METADATA_PATH):
    """
    Save FAISS index and metadata to disk.
    
    Args:
        index: FAISS index object
        metadata: Dictionary with metadata (e.g., {'molecule_ids': [...], 'chembl_ids': [...]})
        index_path: Path to save FAISS index
        metadata_path: Path to save metadata
    """
    print(f"💾 Saving FAISS index to {index_path}...")
    faiss.write_index(index, str(index_path))
    print("✅ Index saved")
    
    print(f"💾 Saving metadata to {metadata_path}...")
    with open(metadata_path, 'wb') as f:
        pickle.dump(metadata, f)
    print("✅ Metadata saved")


def load_index(index_path: Path = INDEX_PATH, metadata_path: Path = METADATA_PATH) -> Tuple[Optional[faiss.Index], Optional[dict]]:
    """
    Load FAISS index and metadata from disk.
    
    Args:
        index_path: Path to FAISS index file
        metadata_path: Path to metadata file
        
    Returns:
        Tuple of (index, metadata) or (None, None) if files don't exist
    """
    if not index_path.exists() or not metadata_path.exists():
        return None, None
    
    print(f"📂 Loading FAISS index from {index_path}...")
    index = faiss.read_index(str(index_path))
    print(f"✅ Loaded index with {index.ntotal} vectors")
    
    print(f"📂 Loading metadata from {metadata_path}...")
    with open(metadata_path, 'rb') as f:
        metadata = pickle.load(f)
    print("✅ Metadata loaded")
    
    return index, metadata


def build_and_save_index(fingerprints: np.ndarray, molecule_ids: list, chembl_ids: list = None, 
                         index_type: str = "L2", force_rebuild: bool = False) -> Tuple[faiss.Index, dict]:
    """
    Build and save FAISS index, using cache if available.
    
    Args:
        fingerprints: Fingerprint matrix (n_molecules, n_bits)
        molecule_ids: List of molecule IDs (indices or custom IDs)
        chembl_ids: Optional list of ChEMBL IDs
        index_type: Type of index ("L2" or "cosine")
        force_rebuild: If True, rebuild even if cache exists
        
    Returns:
        Tuple of (index, metadata dictionary)
    """
    # Try to load from cache
    if not force_rebuild:
        index, metadata = load_index()
        if index is not None and metadata is not None:
            # Verify index size matches
            if index.ntotal == len(fingerprints):
                return index, metadata
            else:
                print(f"⚠️  Cached index size ({index.ntotal}) doesn't match fingerprints ({len(fingerprints)}), rebuilding...")
    
    # Build index
    index = build_faiss_index(fingerprints, index_type=index_type)
    
    # Prepare metadata
    metadata = {
        'molecule_ids': molecule_ids,
        'index_type': index_type,
        'dimension': fingerprints.shape[1],
        'n_vectors': len(fingerprints)
    }
    
    if chembl_ids is not None:
        metadata['chembl_ids'] = chembl_ids
    
    # Save to disk
    save_index(index, metadata)
    
    return index, metadata


if __name__ == "__main__":
    # Test index building
    from fingerprints import load_fingerprints, compute_and_save_fingerprints
    from data_loader import get_molecules
    
    print("🧪 Testing FAISS index building...")
    
    # Load or compute fingerprints
    fingerprints, metadata_df = load_fingerprints()
    if fingerprints is None:
        print("No cached fingerprints found. Computing from molecules...")
        df = get_molecules(max_molecules=1000)
        fingerprints, metadata_df = compute_and_save_fingerprints(df)
    
    # Build index
    molecule_ids = list(range(len(fingerprints)))
    chembl_ids = metadata_df['chembl_id'].tolist() if 'chembl_id' in metadata_df.columns else None
    
    index, index_metadata = build_and_save_index(
        fingerprints, 
        molecule_ids, 
        chembl_ids=chembl_ids,
        index_type="L2",
        force_rebuild=False
    )
    
    print(f"\n📊 Index summary:")
    print(f"  Total vectors: {index.ntotal}")
    print(f"  Dimension: {index_metadata['dimension']}")
    print(f"  Index type: {index_metadata['index_type']}")
    
    # Test search
    print(f"\n🔍 Testing search with first molecule as query...")
    query_fp = fingerprints[0:1]  # First molecule as query
    k = 5
    distances, indices = index.search(query_fp, k)
    
    print(f"  Top {k} similar molecules:")
    for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
        if chembl_ids:
            print(f"    {i+1}. ChEMBL ID: {chembl_ids[idx]}, Distance: {dist:.4f}")
        else:
            print(f"    {i+1}. Index: {idx}, Distance: {dist:.4f}")

