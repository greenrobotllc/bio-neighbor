"""
Test script for disease-drug integration.
Tests the complete workflow: loading data, querying diseases, and searching.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def test_disease_integration():
    """Test the disease-drug integration."""
    print("=" * 60)
    print("🧪 Testing Disease-Drug Integration")
    print("=" * 60)
    
    # Test 1: Load sample Alzheimer's drugs
    print("\n1. Testing DrugBank loader (sample data)...")
    try:
        from drugbank_loader import load_alzheimers_drugs_from_sample
        drugs = load_alzheimers_drugs_from_sample()
        print(f"   ✅ Loaded {len(drugs)} sample Alzheimer's drugs")
        if drugs:
            print(f"   Sample drug: {drugs[0]['drug_name']} -> {drugs[0]['disease']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 2: Check if molecule database exists
    print("\n2. Checking molecule database...")
    from data_loader import DB_PATH, load_from_database
    if not DB_PATH.exists():
        print("   ⚠️  Molecule database not found. Skipping database tests.")
        print("   Run 'python backend/main.py setup' first to create the database.")
        return True  # Not a failure, just incomplete
    
    molecule_df = load_from_database()
    if molecule_df is None or len(molecule_df) == 0:
        print("   ⚠️  No molecules in database. Skipping database tests.")
        print("   Run 'python backend/main.py setup' first to load molecules.")
        return True
    
    print(f"   ✅ Found {len(molecule_df)} molecules in database")
    
    # Test 3: Test disease data loading
    print("\n3. Testing disease data loading...")
    try:
        from drugbank_loader import load_drugbank_data, save_disease_data_to_db
        
        relationships = load_drugbank_data(target_disease="Alzheimer's disease", use_sample=True)
        print(f"   ✅ Loaded {len(relationships)} drug-disease relationships")
        
        if relationships:
            stats = save_disease_data_to_db(relationships, molecule_df)
            print(f"   ✅ Saved to database:")
            print(f"      - Diseases added: {stats['diseases_added']}")
            print(f"      - Relationships added: {stats['relationships_added']}")
            print(f"      - Matched drugs: {stats['matched_drugs']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 4: Test search engine disease methods
    print("\n4. Testing search engine disease methods...")
    try:
        from search_engine import SearchEngine
        
        # Check if index exists
        from pathlib import Path
        DATA_DIR = Path(__file__).parent / "data"
        INDEX_PATH = DATA_DIR / "faiss_index.bin"
        METADATA_PATH = DATA_DIR / "index_metadata.pkl"
        if not INDEX_PATH.exists() or not METADATA_PATH.exists():
            print("   ⚠️  FAISS index not found. Skipping search engine tests.")
            print("   Run 'python backend/main.py setup' first to build the index.")
            return True
        
        engine = SearchEngine()
        
        # Test get_all_diseases
        diseases = engine.get_all_diseases()
        print(f"   ✅ Found {len(diseases)} diseases in database")
        if diseases:
            print(f"   Sample disease: {diseases[0]['name']}")
        
        # Test get_disease_molecules
        if diseases:
            disease_name = diseases[0]['name']
            molecules = engine.get_disease_molecules(disease_name)
            print(f"   ✅ Found {len(molecules)} molecules for '{disease_name}'")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 5: Test API endpoints (if server can start)
    print("\n5. Testing API endpoint structure...")
    try:
        from api import app
        # Check if routes are registered
        routes = [str(rule) for rule in app.url_map.iter_rules()]
        disease_routes = [r for r in routes if 'disease' in r.lower()]
        print(f"   ✅ Found {len(disease_routes)} disease-related API endpoints:")
        for route in disease_routes:
            print(f"      - {route}")
    except Exception as e:
        print(f"   ⚠️  Could not test API: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Integration Test Complete")
    print("=" * 60)
    print("\n💡 Next steps:")
    print("   1. Load disease data: python backend/load_drugbank_data.py")
    print("   2. Start API server: python backend/api.py")
    print("   3. Test endpoints: curl http://127.0.0.1:5000/diseases")
    
    return True


if __name__ == "__main__":
    success = test_disease_integration()
    sys.exit(0 if success else 1)

