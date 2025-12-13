"""
ClinicalTrials.gov API loader for finding drugs by disease/condition.
Uses clinical trial data to find drugs being studied or used for specific conditions.

API Documentation: https://clinicaltrials.gov/api
"""

import requests
import time
import json
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
    seen_interventions = set()
    base_url = "https://clinicaltrials.gov/api/v2/studies"
    page_token = None
    
    try:
        # Pagination loop: continue until we have enough results or no more pages
        while len(drugs) < max_results:
            # ClinicalTrials.gov API v2 query format
            # Search for studies with this condition
            remaining_needed = max_results - len(drugs)
            params = {
                'query.cond': condition,  # Condition search
                'filter.overallStatus': 'RECRUITING|ACTIVE_NOT_RECRUITING|COMPLETED',  # Active or completed studies
                'pageSize': min(remaining_needed, 100),  # Max 100 per page, request only what we need
            }
            
            # Add page token for pagination (if we have one)
            if page_token:
                params['pageToken'] = page_token
            
            # Make request with User-Agent header and handle rate limiting
            headers = {
                'User-Agent': 'BioNeighbor/1.0 (Molecular Similarity Engine)'
            }
            
            max_retries = 3
            retry_count = 0
            response = None
            
            while retry_count < max_retries:
                try:
                    response = requests.get(base_url, params=params, headers=headers, timeout=30)
                    
                    # Handle 429 rate limiting with Retry-After header
                    if response.status_code == 429:
                        retry_after = response.headers.get('Retry-After', '60')  # Default to 60 seconds
                        try:
                            wait_time = int(retry_after)
                        except (ValueError, TypeError):
                            wait_time = 60  # Fallback to 60 seconds if header is invalid
                        
                        if retry_count < max_retries - 1:
                            print(f"  ⚠️  Rate limited (429). Waiting {wait_time} seconds before retry {retry_count + 1}/{max_retries}...")
                            time.sleep(wait_time)
                            retry_count += 1
                            continue
                        else:
                            print(f"  ⚠️  Rate limited (429) after {max_retries} attempts. Returning partial results.")
                            break
                    
                    # Raise for other non-2xx status codes
                    response.raise_for_status()
                    break  # Success, exit retry loop
                    
                except requests.exceptions.RequestException as e:
                    print(f"  ⚠️  API request failed: {e}")
                    # If this is the first page, fail completely; otherwise return what we have
                    if page_token is None:
                        return []
                    break  # Return partial results
            
            # If we don't have a valid response, return what we have
            if response is None or response.status_code != 200:
                if page_token is None:
                    return []
                break  # Return partial results
            
            # Parse JSON response with error handling
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                print(f"  ⚠️  Failed to parse JSON response: {e}")
                # If this is the first page, fail completely; otherwise return what we have
                if page_token is None:
                    return []
                break  # Return partial results
            
            if 'studies' not in data:
                break  # No more studies
            
            # Extract drugs from this page
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
            
            # Check for next page token
            page_token = data.get('nextPageToken')
            if not page_token:
                break  # No more pages
            
            # Rate limiting between pages - be respectful
            time.sleep(1)
            
            # If we have enough results, stop paginating
            if len(drugs) >= max_results:
                break
    
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

