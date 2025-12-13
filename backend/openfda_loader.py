"""
openFDA API loader for finding drugs by disease/condition.
Uses FDA drug labels and approval data to find drugs for specific conditions.

API Documentation: https://open.fda.gov/apis/drug/drugsfda/
"""

import requests
import time
from typing import List, Dict, Optional
from urllib.parse import quote


def search_drugs_by_condition(condition: str, max_results: int = 50) -> List[Dict]:
    """
    Search FDA-approved drugs for a specific condition using openFDA API.
    
    Args:
        condition: Disease or condition name (e.g., "asthma", "diabetes")
        max_results: Maximum number of drugs to return
        
    Returns:
        List of dictionaries with drug information
    """
    print(f"🔍 Searching openFDA for drugs treating '{condition}'...")
    
    drugs = []
    base_url = "https://api.fda.gov/drug/label.json"
    
    # Search for drugs with this condition in their indications
    # openFDA uses a search syntax: search=indications_and_usage:"condition"
    search_query = f'indications_and_usage:"{condition}"'
    
    try:
        params = {
            'search': search_query,
            'limit': min(max_results, 100),  # openFDA max is 100 per request
        }
        
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if 'results' in data:
            for result in data['results']:
                try:
                    # Extract drug information
                    drug_name = None
                    generic_name = None
                    brand_names = []
                    
                    # Get openfda data (structured)
                    openfda = result.get('openfda', {})
                    if openfda:
                        generic_name = openfda.get('generic_name', [None])[0] if openfda.get('generic_name') else None
                        brand_name_list = openfda.get('brand_name', [])
                        if brand_name_list:
                            brand_names = brand_name_list
                            drug_name = brand_name_list[0]  # Use first brand name
                    
                    # Fallback to product_ndc or spl_product_data_elements
                    if not drug_name:
                        product_ndc = result.get('products', [{}])[0].get('product_ndc') if result.get('products') else None
                        if product_ndc:
                            drug_name = f"NDC_{product_ndc}"
                    
                    # Get indications
                    indications = result.get('indications_and_usage', [])
                    indication_text = ' '.join(indications) if isinstance(indications, list) else str(indications)
                    
                    # Get description
                    description = result.get('description', [])
                    description_text = ' '.join(description) if isinstance(description, list) else str(description)
                    
                    if drug_name:
                        drugs.append({
                            'name': drug_name,
                            'generic_name': generic_name,
                            'brand_names': brand_names,
                            'indication': indication_text,
                            'description': description_text,
                            'source': 'openfda',
                            'fda_data': {
                                'product_ndc': result.get('products', [{}])[0].get('product_ndc') if result.get('products') else None,
                                'spl_id': result.get('spl_id'),
                                'spl_set_id': result.get('spl_set_id'),
                            }
                        })
                        
                        if len(drugs) % 10 == 0:
                            print(f"  ✓ Found {len(drugs)} drugs...")
                
                except Exception as e:
                    print(f"  ⚠️  Error parsing drug: {e}")
                    continue
        
        # Rate limiting - openFDA recommends 1 request per second
        time.sleep(1)
        
        # If we got less than max_results, try a broader search
        if len(drugs) < max_results:
            # Try searching in description as well
            search_query2 = f'description:"{condition}"'
            params2 = {
                'search': search_query2,
                'limit': min(max_results - len(drugs), 100),
            }
            
            try:
                response2 = requests.get(base_url, params=params2, timeout=30)
                response2.raise_for_status()
                data2 = response2.json()
                
                if 'results' in data2:
                    for result in data2['results']:
                        # Avoid duplicates
                        existing_names = {d['name'] for d in drugs}
                        
                        openfda = result.get('openfda', {})
                        drug_name = None
                        if openfda.get('brand_name'):
                            drug_name = openfda['brand_name'][0]
                        elif openfda.get('generic_name'):
                            drug_name = openfda['generic_name'][0]
                        
                        if drug_name and drug_name not in existing_names:
                            drugs.append({
                                'name': drug_name,
                                'generic_name': openfda.get('generic_name', [None])[0] if openfda.get('generic_name') else None,
                                'brand_names': openfda.get('brand_name', []),
                                'indication': ' '.join(result.get('indications_and_usage', [])) if isinstance(result.get('indications_and_usage'), list) else str(result.get('indications_and_usage', '')),
                                'description': ' '.join(result.get('description', [])) if isinstance(result.get('description'), list) else str(result.get('description', '')),
                                'source': 'openfda',
                                'fda_data': {
                                    'product_ndc': result.get('products', [{}])[0].get('product_ndc') if result.get('products') else None,
                                }
                            })
                            
                            if len(drugs) >= max_results:
                                break
                
                time.sleep(1)
            except Exception as e:
                print(f"  ⚠️  Error in secondary search: {e}")
    
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Error querying openFDA: {e}")
        return []
    
    print(f"✅ Found {len(drugs)} drugs from openFDA for '{condition}'")
    return drugs[:max_results]


def search_drugs_by_adverse_event(condition: str, max_results: int = 50) -> List[Dict]:
    """
    Search for drugs associated with adverse events related to a condition.
    This can help find drugs that might be contraindicated or have warnings.
    
    Args:
        condition: Disease or condition name
        max_results: Maximum number of results
        
    Returns:
        List of drug information
    """
    print(f"🔍 Searching openFDA adverse events for '{condition}'...")
    
    # This would use the adverse events endpoint
    # For now, we'll focus on the label search which is more direct
    return []


if __name__ == "__main__":
    # Test the loader
    print("🧪 Testing openFDA loader...")
    
    try:
        drugs = search_drugs_by_condition("asthma", max_results=10)
        
        print(f"\n📊 Found {len(drugs)} drugs:")
        for drug in drugs[:5]:
            print(f"  - {drug['name']} ({drug.get('generic_name', 'N/A')})")
            if drug.get('indication'):
                print(f"    Indication: {drug['indication'][:100]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

