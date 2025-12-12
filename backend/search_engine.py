"""
Molecular similarity search engine.
Provides search functionality using FAISS index and RDKit fingerprints.
"""

import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rdkit import Chem
from rdkit.Chem import AllChem
import pandas as pd

from index_builder import load_index
from fingerprints import compute_morgan_fingerprint, FINGERPRINT_SIZE, RADIUS
from data_loader import get_molecule_by_id, load_from_database

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
INDEX_PATH = DATA_DIR / "faiss_index.bin"
METADATA_PATH = DATA_DIR / "index_metadata.pkl"


class SearchEngine:
    """Molecular similarity search engine."""
    
    def __init__(self, index_path: Path = INDEX_PATH, metadata_path: Path = METADATA_PATH):
        """
        Initialize the search engine by loading FAISS index and metadata.
        
        Args:
            index_path: Path to FAISS index file
            metadata_path: Path to metadata file
        """
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = None
        self.metadata = None
        self.molecule_df = None
        
        self._load_index()
        self._load_molecule_data()
    
    def _load_index(self):
        """Load FAISS index and metadata."""
        self.index, self.metadata = load_index(self.index_path, self.metadata_path)
        if self.index is None or self.metadata is None:
            raise RuntimeError(
                f"FAISS index not found. Please run index_builder.py first.\n"
                f"Expected files: {self.index_path}, {self.metadata_path}"
            )
        print(f"✅ Search engine initialized with {self.index.ntotal} molecules")
    
    def _load_molecule_data(self):
        """Load molecule data from database for metadata retrieval."""
        try:
            self.molecule_df = load_from_database()
            if self.molecule_df is None:
                print("⚠️  Warning: Could not load molecule database. Metadata may be limited.")
        except Exception as e:
            print(f"⚠️  Warning: Could not load molecule database: {e}")
    
    def _get_molecule_info(self, index: int) -> Dict:
        """
        Get molecule information by index.
        
        Args:
            index: Index in the FAISS index
            
        Returns:
            Dictionary with molecule information
        """
        if self.molecule_df is not None and index < len(self.molecule_df):
            row = self.molecule_df.iloc[index]
            return {
                'index': int(index),
                'chembl_id': row.get('chembl_id', ''),
                'name': row.get('name', ''),
                'smiles': row.get('smiles', ''),
                'molecular_weight': float(row.get('molecular_weight', 0)),
                'is_approved': bool(row.get('is_approved', False))
            }
        else:
            # Fallback to metadata
            chembl_id = self.metadata.get('chembl_ids', [])[index] if 'chembl_ids' in self.metadata else None
            return {
                'index': int(index),
                'chembl_id': chembl_id or f'molecule_{index}',
                'name': '',
                'smiles': '',
                'molecular_weight': 0,
                'is_approved': False
            }
    
    def search_similar(self, query_smiles: str, top_k: int = 10) -> List[Dict]:
        """
        Search for similar molecules given a query SMILES string.
        
        Args:
            query_smiles: SMILES string of query molecule
            top_k: Number of similar molecules to return
            
        Returns:
            List of dictionaries with similar molecules, each containing:
            - index: Index in the database
            - chembl_id: ChEMBL ID
            - name: Molecule name
            - smiles: SMILES string
            - similarity_score: Similarity score (lower distance = higher similarity)
            - molecular_weight: Molecular weight
            - is_approved: Whether it's an approved drug
        """
        # Compute fingerprint for query molecule
        query_fp = compute_morgan_fingerprint(query_smiles)
        if query_fp is None:
            raise ValueError(f"Invalid SMILES string: {query_smiles}")
        
        # Reshape for FAISS (needs 2D array)
        query_fp = query_fp.reshape(1, -1).astype(np.float32)
        
        # Normalize if using cosine similarity
        if self.metadata.get('index_type') == 'cosine':
            faiss.normalize_L2(query_fp)
        
        # Search FAISS index
        distances, indices = self.index.search(query_fp, min(top_k, self.index.ntotal))
        
        # Build results
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:  # Invalid index
                continue
            
            molecule_info = self._get_molecule_info(int(idx))
            molecule_info['similarity_score'] = float(dist)
            # Convert distance to similarity (for L2, lower distance = higher similarity)
            # For cosine, distance is already similarity-like
            molecule_info['similarity'] = 1.0 / (1.0 + dist) if dist > 0 else 1.0
            results.append(molecule_info)
        
        return results
    
    def search_by_chembl_id(self, chembl_id: str, top_k: int = 10) -> List[Dict]:
        """
        Search for similar molecules given a ChEMBL ID.
        
        Args:
            chembl_id: ChEMBL ID of query molecule
            top_k: Number of similar molecules to return
            
        Returns:
            List of dictionaries with similar molecules
        """
        # Find the molecule in the database
        if self.molecule_df is None:
            raise RuntimeError("Molecule database not loaded")
        
        matches = self.molecule_df[self.molecule_df['chembl_id'] == chembl_id]
        if len(matches) == 0:
            raise ValueError(f"Molecule with ChEMBL ID {chembl_id} not found in database")
        
        smiles = matches.iloc[0]['smiles']
        return self.search_similar(smiles, top_k=top_k)
    
    def get_molecule_by_index(self, index: int) -> Dict:
        """
        Get molecule information by index.
        
        Args:
            index: Index in the FAISS index
            
        Returns:
            Dictionary with molecule information
        """
        return self._get_molecule_info(index)


# Global search engine instance (lazy loading)
_search_engine = None


def get_search_engine() -> SearchEngine:
    """Get or create the global search engine instance."""
    global _search_engine
    if _search_engine is None:
        _search_engine = SearchEngine()
    return _search_engine


def search_similar(query_smiles: str, top_k: int = 10) -> List[Dict]:
    """
    Convenience function to search for similar molecules.
    
    Args:
        query_smiles: SMILES string of query molecule
        top_k: Number of similar molecules to return
        
    Returns:
        List of dictionaries with similar molecules
    """
    engine = get_search_engine()
    return engine.search_similar(query_smiles, top_k=top_k)


if __name__ == "__main__":
    # Test the search engine
    print("🧪 Testing search engine...")
    
    # Initialize engine
    engine = get_search_engine()
    
    # Test searches with known drugs
    test_queries = [
        ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
        ("Caffeine", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"),
        ("Ibuprofen", "CC(C)Cc1ccc(C(C)C(=O)O)cc1")
    ]
    
    for name, smiles in test_queries:
        print(f"\n🔍 Searching for molecules similar to {name} ({smiles})...")
        try:
            results = engine.search_similar(smiles, top_k=5)
            print(f"  Found {len(results)} similar molecules:")
            for i, result in enumerate(results, 1):
                print(f"    {i}. {result['name'] or result['chembl_id']} "
                      f"(similarity: {result['similarity']:.4f}, "
                      f"distance: {result['similarity_score']:.4f})")
        except Exception as e:
            print(f"  ❌ Error: {e}")

