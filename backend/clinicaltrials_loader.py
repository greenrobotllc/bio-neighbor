"""
ClinicalTrials.gov API loader for finding drugs by disease/condition.
Uses clinical trial data to find drugs being studied or used for specific conditions.

API Documentation: https://clinicaltrials.gov/api
"""

import requests
import time
from typing import List, Dict


def search_drugs_by_condition(condition: str, max_results: int = 50) -> List[Dict]:
    """
    Search ClinicalTrials.gov for drugs/interventions used in trials for a condition.
    
    Args:
        condition: Disease or condition name (e.g., "Type 2 Diabetes", "asthma")
        max_results: Maximum number of drugs to return
        
    Returns:
        List of dictionaries with drug/intervention information
    """
    print(f"🔍 Searching ClinicalTrials.gov for interventions treating '{condition}'...")
    
    drugs = []
    base_url = "https://clinicaltrials.gov/api/v2/studies"
    
    try:
        # ClinicalTrials.gov API v2 query format
        # Search for studies with this condition
        params = {
            'query.cond': condition,  # Condition search
            'filter.overallStatus': 'RECRUITING|ACTIVE_NOT_RECRUITING|COMPLETED',  # Active or completed studies
            'pageSize': min(max_results, 100),  # Max 100 per page
            'pageToken': '',  # For pagination
        }
        
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if 'studies' in data:
            seen_interventions = set()
            
            for study in data['studies']:
                try:
                    # Extract interventions (drugs) from the study
                    protocol_section = study.get('protocolSection', {})
                    arms_interventions = protocol_section.get('armsInterventionsModule', {})
                    interventions = arms_interventions.get('interventions', [])
                    
                    for intervention in interventions:
                        intervention_name = intervention.get('name', '').strip()
                        intervention_type = intervention.get('type', '').strip()
                        
                        # Focus on drug interventions
                        if intervention_type.upper() in ['DRUG', 'BIOLOGICAL', 'PHARMACEUTICAL']:
                            if intervention_name and intervention_name not in seen_interventions:
                                seen_interventions.add(intervention_name)
                                
                                # Get condition from study
                                conditions_module = protocol_section.get('conditionsModule', {})
                                conditions = conditions_module.get('conditions', [])
                                # Conditions is an array of strings, not dicts
                                condition_list = conditions if isinstance(conditions, list) else []
                                
                                # Get description
                                description_module = protocol_section.get('descriptionModule', {})
                                brief_summary = description_module.get('briefSummary', '')
                                
                                drugs.append({
                                    'name': intervention_name,
                                    'intervention_type': intervention_type,
                                    'conditions': condition_list,
                                    'description': brief_summary,
                                    'source': 'clinicaltrials',
                                    'trial_data': {
                                        'nct_id': study.get('protocolSection', {}).get('identificationModule', {}).get('nctId'),
                                        'study_title': protocol_section.get('identificationModule', {}).get('briefTitle', ''),
                                    }
                                })
                                
                                if len(drugs) % 10 == 0:
                                    print(f"  ✓ Found {len(drugs)} interventions...")
                                
                                if len(drugs) >= max_results:
                                    break
                    
                    if len(drugs) >= max_results:
                        break
                
                except (KeyError, TypeError, ValueError) as e:
                    # Catch expected data-shape errors (missing keys, wrong types, invalid values)
                    print(f"  ⚠️  Error parsing study: {e}")
                    continue
        
        # Rate limiting - be respectful
        time.sleep(1)
    
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Error querying ClinicalTrials.gov: {e}")
        return []
    
    print(f"✅ Found {len(drugs)} interventions from ClinicalTrials.gov for '{condition}'")
    return drugs[:max_results]


if __name__ == "__main__":
    # Test the loader
    print("🧪 Testing ClinicalTrials.gov loader...")
    
    try:
        drugs = search_drugs_by_condition("Type 2 Diabetes", max_results=10)
        
        print(f"\n📊 Found {len(drugs)} interventions:")
        for drug in drugs[:5]:
            print(f"  - {drug['name']} ({drug.get('intervention_type', 'N/A')})")
            if drug.get('conditions'):
                print(f"    Conditions: {', '.join(drug['conditions'][:3])}")
    except Exception as e:
        print(f"❌ Error: {e}")

