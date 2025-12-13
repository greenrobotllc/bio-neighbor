"""
Multi-API disease-drug loader.
Combines multiple APIs (openFDA, ClinicalTrials.gov, PubChem, RxNorm) to find drugs by disease.
Uses a fallback chain for best results.
"""

import time
from typing import List, Dict, Optional
from pathlib import Path

# Try importing API loaders
try:
    from openfda_loader import search_drugs_by_condition as openfda_search
    OPENFDA_AVAILABLE = True
except ImportError:
    OPENFDA_AVAILABLE = False
    openfda_search = None

try:
    from clinicaltrials_loader import search_drugs_by_condition as clinicaltrials_search
    CLINICALTRIALS_AVAILABLE = True
except ImportError:
    CLINICALTRIALS_AVAILABLE = False
    clinicaltrials_search = None

try:
    from pubchem_disease_loader import search_drugs_by_disease as pubchem_search
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False
    pubchem_search = None

try:
    from download_drugs_rxnorm import search_rxnorm_drugs
    RXNORM_AVAILABLE = True
except ImportError:
    RXNORM_AVAILABLE = False
    search_rxnorm_drugs = None


def search_drugs_by_disease_multi_api(
    disease_name: str,
    max_drugs: int = 50,
    preferred_apis: Optional[List[str]] = None
) -> List[Dict]:
    """
    Search for drugs by disease using multiple APIs with fallback.
    
    Strategy:
    1. openFDA (FDA-approved drugs) - most authoritative for approved drugs
    2. ClinicalTrials.gov (drugs in trials) - good for experimental/emerging drugs
    3. PubChem (text search) - fallback for broader coverage
    4. RxNorm (if disease maps to drug concepts) - for standardized names
    
    Args:
        disease_name: Name of the disease/condition
        max_drugs: Maximum number of drugs to return
        preferred_apis: List of API names to prefer (e.g., ['openfda', 'clinicaltrials'])
        
    Returns:
        List of drug dictionaries with source information
    """
    print(f"🔍 Multi-API search for drugs treating '{disease_name}'...")
    print(f"   Available APIs: openFDA={OPENFDA_AVAILABLE}, ClinicalTrials={CLINICALTRIALS_AVAILABLE}, PubChem={PUBCHEM_AVAILABLE}, RxNorm={RXNORM_AVAILABLE}")
    
    all_drugs = []
    seen_names = set()  # Track by name to avoid duplicates
    
    preferred_apis = preferred_apis or ['openfda', 'clinicaltrials', 'pubchem']
    
    # 1. Try openFDA first (FDA-approved drugs)
    if 'openfda' in preferred_apis and OPENFDA_AVAILABLE and openfda_search:
        try:
            print(f"\n📋 [1/4] Searching openFDA (FDA-approved drugs) for '{disease_name}'...")
            import sys
            sys.stdout.flush()
            api_start = time.time()
            fda_drugs = openfda_search(disease_name, max_results=max_drugs)
            api_time = time.time() - api_start
            
            for drug in fda_drugs:
                drug_name = drug.get('name') or drug.get('generic_name')
                if drug_name and drug_name.lower() not in seen_names:
                    seen_names.add(drug_name.lower())
                    drug['api_source'] = 'openfda'
                    all_drugs.append(drug)
            
            fda_count = len([d for d in all_drugs if d.get('api_source') == 'openfda'])
            print(f"   ✓ Found {fda_count} drugs from openFDA in {api_time:.1f}s")
            sys.stdout.flush()
        except Exception as e:
            print(f"   ⚠️  openFDA search failed: {e}")
            import sys
            sys.stdout.flush()
    
    # 2. Try ClinicalTrials.gov (drugs in clinical trials)
    if len(all_drugs) < max_drugs and 'clinicaltrials' in preferred_apis and CLINICALTRIALS_AVAILABLE and clinicaltrials_search:
        try:
            remaining = max_drugs - len(all_drugs)
            print(f"\n🧪 [2/4] Searching ClinicalTrials.gov (drugs in trials) for '{disease_name}'...")
            print(f"   Target: {remaining} more drugs needed")
            import sys
            sys.stdout.flush()
            api_start = time.time()
            trial_drugs = clinicaltrials_search(disease_name, max_results=remaining)
            api_time = time.time() - api_start
            
            for drug in trial_drugs:
                drug_name = drug.get('name')
                if drug_name and drug_name.lower() not in seen_names:
                    seen_names.add(drug_name.lower())
                    drug['api_source'] = 'clinicaltrials'
                    all_drugs.append(drug)
            
            trials_count = len([d for d in all_drugs if d.get('api_source') == 'clinicaltrials'])
            print(f"   ✓ Found {trials_count} interventions from ClinicalTrials.gov in {api_time:.1f}s")
            sys.stdout.flush()
        except Exception as e:
            print(f"   ⚠️  ClinicalTrials.gov search failed: {e}")
            import sys
            sys.stdout.flush()
    
    # 3. Fallback to PubChem (text search)
    if len(all_drugs) < max_drugs and 'pubchem' in preferred_apis and PUBCHEM_AVAILABLE and pubchem_search:
        try:
            remaining = max_drugs - len(all_drugs)
            print(f"\n🧬 [3/4] Searching PubChem (text-based search) for '{disease_name}'...")
            print(f"   Target: {remaining} more drugs needed")
            import sys
            sys.stdout.flush()
            api_start = time.time()
            pubchem_drugs = pubchem_search(disease_name, max_drugs=remaining)
            api_time = time.time() - api_start
            
            for drug in pubchem_drugs:
                drug_name = drug.get('name')
                if drug_name and drug_name.lower() not in seen_names:
                    seen_names.add(drug_name.lower())
                    drug['api_source'] = 'pubchem'
                    all_drugs.append(drug)
            
            pubchem_count = len([d for d in all_drugs if d.get('api_source') == 'pubchem'])
            print(f"   ✓ Found {pubchem_count} drugs from PubChem in {api_time:.1f}s")
            sys.stdout.flush()
        except Exception as e:
            print(f"   ⚠️  PubChem search failed: {e}")
            import sys
            sys.stdout.flush()
    
    # 4. Try RxNorm if we have very few results (for standardized names)
    if len(all_drugs) < max_drugs // 2 and RXNORM_AVAILABLE and search_rxnorm_drugs:
        try:
            print("\n💊 Searching RxNorm (standardized drug names)...")
            remaining = max_drugs - len(all_drugs)
            # RxNorm search by disease is indirect - would need to map disease to drug concepts
            # For now, skip this as it requires more complex mapping
            pass
        except Exception as e:
            print(f"   ⚠️  RxNorm search failed: {e}")
    
    print(f"\n✅ Total: {len(all_drugs)} unique drugs found across all APIs")
    
    # Sort by source priority (openFDA > ClinicalTrials > PubChem)
    source_priority = {'openfda': 1, 'clinicaltrials': 2, 'pubchem': 3}
    all_drugs.sort(key=lambda x: source_priority.get(x.get('api_source', 'pubchem'), 99))
    
    return all_drugs[:max_drugs]


def enrich_drug_with_pubchem(drug: Dict) -> Dict:
    """
    Enrich a drug from openFDA or ClinicalTrials with PubChem molecular data.
    This adds SMILES, molecular weight, and other chemical properties.
    
    Args:
        drug: Drug dictionary from openFDA or ClinicalTrials
        
    Returns:
        Enriched drug dictionary with PubChem data
    """
    try:
        import pubchempy as pcp
        
        # Try to find the drug in PubChem by name
        drug_name = drug.get('name') or drug.get('generic_name')
        if not drug_name:
            return drug
        
        compounds = pcp.get_compounds(drug_name, 'name')
        if compounds:
            comp = compounds[0]
            
            # Add PubChem data
            drug['pubchem_cid'] = str(comp.cid) if comp.cid else None
            drug['smiles'] = comp.connectivity_smiles or comp.canonical_smiles or comp.isomeric_smiles
            drug['molecular_weight'] = comp.molecular_weight
            drug['formula'] = comp.molecular_formula
            
            time.sleep(0.2)  # Rate limiting
        
    except Exception as e:
        # If PubChem enrichment fails, return original drug
        pass
    
    return drug


if __name__ == "__main__":
    # Test the multi-API loader
    print("🧪 Testing Multi-API Disease Drug Loader...")
    print("=" * 60)
    
    test_diseases = ["asthma", "Type 2 Diabetes", "schizophrenia"]
    
    for disease in test_diseases:
        print(f"\n🔍 Testing: {disease}")
        print("-" * 60)
        
        try:
            drugs = search_drugs_by_disease_multi_api(disease, max_drugs=20)
            
            print(f"\n📊 Results for '{disease}':")
            print(f"   Total drugs found: {len(drugs)}")
            
            # Group by source
            by_source = {}
            for drug in drugs:
                source = drug.get('api_source', 'unknown')
                by_source[source] = by_source.get(source, 0) + 1
            
            print(f"   By source: {by_source}")
            
            # Show sample
            for drug in drugs[:3]:
                print(f"   - {drug.get('name')} (from {drug.get('api_source', 'unknown')})")
        
        except Exception as e:
            print(f"   ❌ Error: {e}")

