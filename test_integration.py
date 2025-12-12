#!/usr/bin/env python3
"""
Integration test script for BioNeighbor.
Tests the complete pipeline: data loading → fingerprints → index → search.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from data_loader import get_molecules, load_from_database
from fingerprints import compute_and_save_fingerprints, load_fingerprints
from index_builder import build_and_save_index, load_index
from search_engine import SearchEngine
from molecule_renderer import render_molecule_2d


def test_data_loading():
    """Test data loading."""
    print("=" * 60)
    print("Test 1: Data Loading")
    print("=" * 60)
    
    try:
        # Try to load from cache first
        df = get_molecules(max_molecules=100, force_download=False)
        assert len(df) > 0, "No molecules loaded"
        assert 'smiles' in df.columns, "Missing 'smiles' column"
        assert 'chembl_id' in df.columns, "Missing 'chembl_id' column"
        print(f"✅ Data loading: {len(df)} molecules loaded")
        return df
    except Exception as e:
        print(f"❌ Data loading failed: {e}")
        raise


def test_fingerprints(df):
    """Test fingerprint computation."""
    print("\n" + "=" * 60)
    print("Test 2: Fingerprint Computation")
    print("=" * 60)
    
    try:
        fingerprints, valid_df = compute_and_save_fingerprints(df, force_recompute=False)
        assert len(fingerprints) > 0, "No fingerprints computed"
        assert fingerprints.shape[1] == 2048, f"Wrong fingerprint size: {fingerprints.shape[1]}"
        assert len(fingerprints) == len(valid_df), "Fingerprint count mismatch"
        print(f"✅ Fingerprints: {len(fingerprints)} computed, size {fingerprints.shape[1]}")
        return fingerprints, valid_df
    except Exception as e:
        print(f"❌ Fingerprint computation failed: {e}")
        raise


def test_index_building(fingerprints, valid_df):
    """Test FAISS index building."""
    print("\n" + "=" * 60)
    print("Test 3: FAISS Index Building")
    print("=" * 60)
    
    try:
        molecule_ids = list(range(len(fingerprints)))
        chembl_ids = valid_df['chembl_id'].tolist() if 'chembl_id' in valid_df.columns else None
        
        index, metadata = build_and_save_index(
            fingerprints,
            molecule_ids,
            chembl_ids=chembl_ids,
            index_type="L2",
            force_rebuild=False
        )
        
        assert index.ntotal == len(fingerprints), "Index size mismatch"
        print(f"✅ Index building: {index.ntotal} vectors indexed")
        return index, metadata
    except Exception as e:
        print(f"❌ Index building failed: {e}")
        raise


def test_search_engine():
    """Test search engine."""
    print("\n" + "=" * 60)
    print("Test 4: Search Engine")
    print("=" * 60)
    
    try:
        engine = SearchEngine()
        
        # Test with aspirin
        test_smiles = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
        results = engine.search_similar(test_smiles, top_k=5)
        
        assert len(results) > 0, "No search results"
        assert all('chembl_id' in r for r in results), "Missing chembl_id in results"
        assert all('similarity' in r for r in results), "Missing similarity in results"
        
        print(f"✅ Search engine: Found {len(results)} similar molecules")
        print(f"   Top result: {results[0].get('name', results[0].get('chembl_id', 'Unknown'))}")
        return True
    except Exception as e:
        print(f"❌ Search engine failed: {e}")
        raise


def test_molecule_rendering():
    """Test molecule rendering."""
    print("\n" + "=" * 60)
    print("Test 5: Molecule Rendering")
    print("=" * 60)
    
    try:
        test_smiles = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
        img = render_molecule_2d(test_smiles, width=400, height=400)
        
        assert img is not None, "Failed to render molecule"
        assert img.size == (400, 400), f"Wrong image size: {img.size}"
        
        print(f"✅ Molecule rendering: Image size {img.size}")
        return True
    except Exception as e:
        print(f"❌ Molecule rendering failed: {e}")
        raise


def main():
    """Run all integration tests."""
    print("\n🧪 BioNeighbor Integration Tests")
    print("=" * 60)
    print()
    
    try:
        # Test 1: Data loading
        df = test_data_loading()
        
        # Test 2: Fingerprints
        fingerprints, valid_df = test_fingerprints(df)
        
        # Test 3: Index building
        index, metadata = test_index_building(fingerprints, valid_df)
        
        # Test 4: Search engine
        test_search_engine()
        
        # Test 5: Molecule rendering
        test_molecule_rendering()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return 0
    
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ Tests failed: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

