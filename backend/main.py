"""
Main CLI entry point for BioNeighbor.
Provides command-line interface for testing and data preparation.
"""

import argparse
import sys
from pathlib import Path

from data_loader import get_molecules
from fingerprints import compute_and_save_fingerprints, load_fingerprints
from index_builder import build_and_save_index, load_index
from search_engine import SearchEngine, get_search_engine


def setup_data(max_molecules: int = 10000, force_download: bool = False):
    """Download and prepare molecule data."""
    print("=" * 60)
    print("📥 Step 1: Loading molecule data")
    print("=" * 60)
    df = get_molecules(force_download=force_download, max_molecules=max_molecules)
    print(f"✅ Loaded {len(df)} molecules\n")
    return df


def setup_fingerprints(df, force_recompute: bool = False):
    """Compute molecular fingerprints."""
    print("=" * 60)
    print("🔬 Step 2: Computing fingerprints")
    print("=" * 60)
    fingerprints, valid_df = compute_and_save_fingerprints(df, force_recompute=force_recompute)
    print(f"✅ Computed {len(fingerprints)} fingerprints\n")
    return fingerprints, valid_df


def setup_index(fingerprints, valid_df, force_rebuild: bool = False):
    """Build FAISS index."""
    print("=" * 60)
    print("🔨 Step 3: Building FAISS index")
    print("=" * 60)
    molecule_ids = list(range(len(fingerprints)))
    chembl_ids = valid_df['chembl_id'].tolist() if 'chembl_id' in valid_df.columns else None
    
    index, metadata = build_and_save_index(
        fingerprints,
        molecule_ids,
        chembl_ids=chembl_ids,
        index_type="L2",
        force_rebuild=force_rebuild
    )
    print(f"✅ Built index with {index.ntotal} vectors\n")
    return index, metadata


def setup_all(max_molecules: int = 10000, force: bool = False):
    """Run complete setup: schema → data → fingerprints → index."""
    print("\n🚀 BioNeighbor Setup")
    print("=" * 60)
    print(f"Max molecules: {max_molecules}")
    print(f"Force rebuild: {force}")
    print("=" * 60 + "\n")
    
    # Step 0: Initialize/migrate database schema
    from db_migrations import migrate_database
    print("🔧 Initializing database schema...")
    if not migrate_database():
        print("❌ Database schema initialization failed")
        return
    print("✅ Database schema ready\n")
    
    # Step 1: Load data
    df = setup_data(max_molecules=max_molecules, force_download=force)
    
    # Step 2: Compute fingerprints
    fingerprints, valid_df = setup_fingerprints(df, force_recompute=force)
    
    # Step 3: Build index
    index, metadata = setup_index(fingerprints, valid_df, force_rebuild=force)
    
    print("=" * 60)
    print("✅ Setup complete! You can now use the search engine.")
    print("=" * 60)


def search_cli(query_smiles: str, top_k: int = 10):
    """Search for similar molecules via CLI."""
    print(f"\n🔍 Searching for molecules similar to: {query_smiles}")
    print("=" * 60)
    
    try:
        engine = get_search_engine()
        results = engine.search_similar(query_smiles, top_k=top_k)
        
        print(f"\nFound {len(results)} similar molecules:\n")
        for i, result in enumerate(results, 1):
            name = result.get('name', '') or result.get('chembl_id', 'Unknown')
            similarity = result.get('similarity', 0)
            mw = result.get('molecular_weight', 0)
            approved = "✓" if result.get('is_approved', False) else " "
            
            print(f"{i:2d}. [{approved}] {name}")
            print(f"     ChEMBL ID: {result.get('chembl_id', 'N/A')}")
            print(f"     Similarity: {similarity:.4f} (distance: {result.get('similarity_score', 0):.4f})")
            print(f"     MW: {mw:.2f} Da")
            print(f"     SMILES: {result.get('smiles', 'N/A')[:80]}...")
            print()
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='BioNeighbor - Molecular Similarity Search Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Complete setup (download data, compute fingerprints, build index)
  python main.py setup --max-molecules 10000

  # Search for similar molecules
  python main.py search "CC(=O)Oc1ccccc1C(=O)O" --top-k 10

  # Search by ChEMBL ID
  python main.py search-chembl CHEMBL25 --top-k 5
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Setup data, fingerprints, and index')
    setup_parser.add_argument('--max-molecules', type=int, default=10000,
                             help='Maximum number of molecules to download (default: 10000)')
    setup_parser.add_argument('--force', action='store_true',
                             help='Force rebuild even if cache exists')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search for similar molecules')
    search_parser.add_argument('smiles', help='SMILES string to search for')
    search_parser.add_argument('--top-k', type=int, default=10,
                              help='Number of results to return (default: 10)')
    
    # Search by ChEMBL ID command
    search_chembl_parser = subparsers.add_parser('search-chembl', help='Search by ChEMBL ID')
    search_chembl_parser.add_argument('chembl_id', help='ChEMBL ID to search for')
    search_chembl_parser.add_argument('--top-k', type=int, default=10,
                                     help='Number of results to return (default: 10)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'setup':
        setup_all(max_molecules=args.max_molecules, force=args.force)
    
    elif args.command == 'search':
        search_cli(args.smiles, top_k=args.top_k)
    
    elif args.command == 'search-chembl':
        try:
            engine = get_search_engine()
            results = engine.search_by_chembl_id(args.chembl_id, top_k=args.top_k)
            print(f"\n🔍 Searching for molecules similar to ChEMBL ID: {args.chembl_id}")
            print("=" * 60)
            print(f"\nFound {len(results)} similar molecules:\n")
            for i, result in enumerate(results, 1):
                name = result.get('name', '') or result.get('chembl_id', 'Unknown')
                similarity = result.get('similarity', 0)
                mw = result.get('molecular_weight', 0)
                approved = "✓" if result.get('is_approved', False) else " "
                
                print(f"{i:2d}. [{approved}] {name}")
                print(f"     ChEMBL ID: {result.get('chembl_id', 'N/A')}")
                print(f"     Similarity: {similarity:.4f}")
                print(f"     MW: {mw:.2f} Da")
                print()
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()

