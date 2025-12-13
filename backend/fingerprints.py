"""
Molecular fingerprint computation using RDKit.
Computes Morgan fingerprints (ECFP4) for molecules.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Optional, Tuple
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
import pickle

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
FINGERPRINTS_PATH = DATA_DIR / "fingerprints.pkl"
FINGERPRINT_SIZE = 2048  # ECFP4 fingerprint size
RADIUS = 2  # ECFP4 radius


def compute_morgan_fingerprint(smiles: str, radius: int = RADIUS, n_bits: int = FINGERPRINT_SIZE) -> Optional[np.ndarray]:
    """
    Compute Morgan fingerprint (ECFP) for a SMILES string.
    
    Args:
        smiles: SMILES string
        radius: Radius for Morgan fingerprint (2 = ECFP4)
        n_bits: Number of bits in fingerprint
        
    Returns:
        NumPy array of fingerprint bits, or None if SMILES is invalid
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        # Compute Morgan fingerprint
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=n_bits)
        return np.array(fp, dtype=np.float32)
    except Exception as e:
        print(f"⚠️  Error computing fingerprint for {smiles[:50]}: {e}")
        return None


def compute_fingerprints_batch(smiles_list: List[str], radius: int = RADIUS, n_bits: int = FINGERPRINT_SIZE) -> Tuple[np.ndarray, List[int]]:
    """
    Compute fingerprints for a batch of SMILES strings.
    
    Args:
        smiles_list: List of SMILES strings
        radius: Radius for Morgan fingerprint
        n_bits: Number of bits in fingerprint
        
    Returns:
        Tuple of (fingerprint matrix, valid indices)
        - fingerprint matrix: (n_valid, n_bits) numpy array
        - valid indices: List of indices in original list that had valid SMILES
    """
    fingerprints = []
    valid_indices = []
    
    print(f"🔬 Computing fingerprints for {len(smiles_list)} molecules...")
    
    for idx, smiles in enumerate(smiles_list):
        fp = compute_morgan_fingerprint(smiles, radius=radius, n_bits=n_bits)
        if fp is not None:
            fingerprints.append(fp)
            valid_indices.append(idx)
        
        if (idx + 1) % 100 == 0:
            print(f"  ✓ Processed {idx + 1}/{len(smiles_list)} molecules ({len(fingerprints)} valid)")
    
    if len(fingerprints) == 0:
        raise ValueError("No valid fingerprints computed!")
    
    fingerprint_matrix = np.vstack(fingerprints)
    print(f"✅ Computed {len(fingerprints)} valid fingerprints")
    
    return fingerprint_matrix, valid_indices


def compute_fingerprints_from_dataframe(df: pd.DataFrame, smiles_column: str = 'smiles') -> Tuple[np.ndarray, pd.DataFrame]:
    """
    Compute fingerprints for all molecules in a DataFrame.
    
    Args:
        df: DataFrame with molecule data
        smiles_column: Name of column containing SMILES strings
        
    Returns:
        Tuple of (fingerprint matrix, filtered DataFrame with valid molecules)
    """
    smiles_list = df[smiles_column].tolist()
    fingerprint_matrix, valid_indices = compute_fingerprints_batch(smiles_list)
    
    # Filter DataFrame to only include valid molecules
    valid_df = df.iloc[valid_indices].copy().reset_index(drop=True)
    
    return fingerprint_matrix, valid_df


def save_fingerprints(fingerprints: np.ndarray, metadata: pd.DataFrame, filepath: Path = FINGERPRINTS_PATH):
    """
    Save fingerprints and metadata to disk.
    
    Args:
        fingerprints: Fingerprint matrix (n_molecules, n_bits)
        metadata: DataFrame with molecule metadata (must have same number of rows as fingerprints)
        filepath: Path to save the pickle file
    """
    if len(fingerprints) != len(metadata):
        raise ValueError(f"Fingerprint matrix ({len(fingerprints)} rows) and metadata ({len(metadata)} rows) must have same length")
    
    print(f"💾 Saving fingerprints to {filepath}...")
    # Ensure target directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        'fingerprints': fingerprints,
        'metadata': metadata
    }
    
    # Note: pickle.load() can execute arbitrary code if the file is tampered with.
    # For production, consider using np.savez_compressed() for arrays and
    # metadata.to_parquet() or CSV for metadata, or ensure the cache location
    # has restricted permissions.
    with open(filepath, 'wb') as f:
        pickle.dump(data, f)
    
    print(f"✅ Saved {len(fingerprints)} fingerprints")


def load_fingerprints(filepath: Path = FINGERPRINTS_PATH) -> Tuple[Optional[np.ndarray], Optional[pd.DataFrame]]:
    """
    Load fingerprints and metadata from disk.
    
    Args:
        filepath: Path to the pickle file
        
    Returns:
        Tuple of (fingerprint matrix, metadata DataFrame) or (None, None) if file doesn't exist
    """
    if not filepath.exists():
        return None, None
    
    print(f"📂 Loading fingerprints from {filepath}...")
    with open(filepath, 'rb') as f:
        data = pickle.load(f)
    
    fingerprints = data['fingerprints']
    metadata = data['metadata']
    
    print(f"✅ Loaded {len(fingerprints)} fingerprints")
    return fingerprints, metadata


def compute_and_save_fingerprints(df: pd.DataFrame, force_recompute: bool = False) -> Tuple[np.ndarray, pd.DataFrame]:
    """
    Compute fingerprints for molecules, using cache if available.
    
    Args:
        df: DataFrame with molecule data (must have 'smiles' column)
        force_recompute: If True, recompute even if cache exists
        
    Returns:
        Tuple of (fingerprint matrix, filtered DataFrame with valid molecules)
    """
    # Try to load from cache
    if not force_recompute:
        fingerprints, metadata = load_fingerprints()
        if fingerprints is not None and metadata is not None:
            return fingerprints, metadata
    
    # Compute fingerprints
    fingerprints, valid_df = compute_fingerprints_from_dataframe(df)
    
    # Save to cache
    save_fingerprints(fingerprints, valid_df)
    
    return fingerprints, valid_df


if __name__ == "__main__":
    # Test fingerprint computation
    from data_loader import get_molecules
    
    print("🧪 Testing fingerprint computation...")
    
    # Load a small subset of molecules
    df = get_molecules(max_molecules=100)
    
    # Compute fingerprints
    fingerprints, valid_df = compute_and_save_fingerprints(df, force_recompute=False)
    
    print(f"\n📊 Fingerprint summary:")
    print(f"  Total molecules: {len(df)}")
    print(f"  Valid fingerprints: {len(fingerprints)}")
    print(f"  Fingerprint size: {fingerprints.shape[1]} bits")
    print(f"  Fingerprint shape: {fingerprints.shape}")
    print(f"\n📝 Sample fingerprints (first 3 molecules, first 20 bits):")
    print(fingerprints[:3, :20])

