"""
API interface for BioNeighbor search engine.
Provides JSON-based API via HTTP (Flask) or stdin/stdout.
"""

import json
import sys
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS

from search_engine import SearchEngine, get_search_engine
from molecule_renderer import render_molecule_to_base64, generate_3d_coordinates

app = Flask(__name__)
CORS(app)  # Enable CORS for local development

# Global search engine instance
_engine: Optional[SearchEngine] = None


def get_engine() -> SearchEngine:
    """Get or initialize the search engine."""
    global _engine
    if _engine is None:
        try:
            _engine = get_search_engine()
        except Exception as e:
            print(f"❌ Error initializing search engine: {e}")
            import traceback
            traceback.print_exc()
            raise
    return _engine


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'BioNeighbor API'})


@app.route('/search', methods=['POST'])
def search():
    """
    Search for similar molecules.
    
    Request body (JSON):
    {
        "query_smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "top_k": 10
    }
    
    Response (JSON):
    {
        "success": true,
        "results": [
            {
                "index": 0,
                "chembl_id": "CHEMBL25",
                "name": "Aspirin",
                "smiles": "...",
                "similarity": 0.95,
                "similarity_score": 0.05,
                "molecular_weight": 180.16,
                "is_approved": true
            },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        query_smiles = data.get('query_smiles')
        if not query_smiles:
            return jsonify({'success': False, 'error': 'query_smiles is required'}), 400
        
        top_k = data.get('top_k', 10)
        if not isinstance(top_k, int) or top_k < 1:
            top_k = 10
        
        # Validate SMILES before attempting search
        from fingerprints import compute_morgan_fingerprint
        query_fp = compute_morgan_fingerprint(query_smiles)
        if query_fp is None:
            return jsonify({
                'success': False, 
                'error': f'Invalid SMILES string: {query_smiles}'
            }), 400
        
        engine = get_engine()
        results = engine.search_similar(query_smiles, top_k=top_k)
        
        return jsonify({
            'success': True,
            'results': results,
            'query_smiles': query_smiles,
            'top_k': len(results)
        })
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except OSError as e:
        # Handle broken pipe and other OS errors
        return jsonify({
            'success': False, 
            'error': f'Backend error: {str(e)}. Please ensure the search engine is properly initialized.'
        }), 500
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /search endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False, 
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/search/chembl', methods=['POST'])
def search_by_chembl_id():
    """
    Search for similar molecules by ChEMBL ID.
    
    Request body (JSON):
    {
        "chembl_id": "CHEMBL25",
        "top_k": 10
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        chembl_id = data.get('chembl_id')
        if not chembl_id:
            return jsonify({'success': False, 'error': 'chembl_id is required'}), 400
        
        top_k = data.get('top_k', 10)
        if not isinstance(top_k, int) or top_k < 1:
            top_k = 10
        
        engine = get_engine()
        results = engine.search_by_chembl_id(chembl_id, top_k=top_k)
        
        return jsonify({
            'success': True,
            'results': results,
            'query_chembl_id': chembl_id,
            'top_k': len(results)
        })
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Internal error: {str(e)}'}), 500


@app.route('/molecules', methods=['GET'])
def list_molecules():
    """
    List molecules with pagination, search, and random options.
    
    Query parameters:
    - page (int): Page number (default: 1)
    - per_page (int): Items per page (default: 20, max: 100)
    - search (string): Search by name (case-insensitive partial match)
    - random (bool): Return random sample instead of paginated results
    - random_count (int): Number of random molecules (default: 20)
    
    Response (JSON):
    {
        "success": true,
        "molecules": [...],
        "pagination": {
            "page": 1,
            "per_page": 20,
            "total": 9993,
            "total_pages": 500
        }
    }
    """
    try:
        # Get query parameters
        random_mode = request.args.get('random', 'false').lower() == 'true'
        
        if random_mode:
            # Random mode
            random_count = request.args.get('random_count', 20, type=int)
            random_count = min(max(random_count, 1), 100)  # Clamp between 1 and 100
            
            engine = get_engine()
            molecules = engine.get_random_molecules(count=random_count)
            
            return jsonify({
                'success': True,
                'molecules': molecules,
                'pagination': None
            })
        else:
            # Pagination mode
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            search = request.args.get('search', None, type=str)
            
            # Clamp per_page between 1 and 100
            per_page = min(max(per_page, 1), 100)
            
            engine = get_engine()
            molecules, pagination = engine.list_molecules(page=page, per_page=per_page, search=search)
            
            return jsonify({
                'success': True,
                'molecules': molecules,
                'pagination': pagination
            })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /molecules endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/molecule/<int:index>', methods=['GET'])
def get_molecule(index: int):
    """
    Get molecule information by index.
    
    Query parameters:
    - include_similar (bool): If true, include similar molecules in response
    - top_k (int): Number of similar molecules to return (default: 10)
    
    Response (JSON):
    {
        "success": true,
        "molecule": {
            "index": 0,
            "chembl_id": "CHEMBL25",
            "name": "Aspirin",
            "smiles": "...",
            "molecular_weight": 180.16,
            "is_approved": true
        },
        "similar": [...]  // Only if include_similar=true
    }
    """
    try:
        include_similar = request.args.get('include_similar', 'false').lower() == 'true'
        top_k = request.args.get('top_k', 10, type=int)
        top_k = min(max(top_k, 1), 50)  # Clamp between 1 and 50
        
        engine = get_engine()
        
        if include_similar:
            result = engine.get_molecule_with_similar(index, top_k=top_k)
            return jsonify({
                'success': True,
                'molecule': result['molecule'],
                'similar': result['similar']
            })
        else:
            molecule = engine.get_molecule_by_index(index)
            return jsonify({
                'success': True,
                'molecule': molecule
            })
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /molecule endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': f'Internal error: {error_msg}'}), 500


@app.route('/molecule/<int:index>/thumbnail', methods=['GET'])
def get_molecule_thumbnail(index: int):
    """
    Get a small thumbnail image of a molecule for use in cards.
    
    Query parameters:
    - width (int): Image width (default: 100)
    - height (int): Image height (default: 100)
    
    Response (JSON):
    {
        "success": true,
        "image": "data:image/png;base64,..."
    }
    """
    try:
        width = request.args.get('width', 100, type=int)
        height = request.args.get('height', 100, type=int)
        
        engine = get_engine()
        molecule = engine.get_molecule_by_index(index)
        
        if not molecule.get('smiles'):
            return jsonify({'success': False, 'error': 'Molecule has no SMILES'}), 400
        
        image_base64 = render_molecule_to_base64(
            molecule['smiles'], 
            width=width, 
            height=height, 
            enhanced=True
        )
        
        if image_base64 is None:
            return jsonify({'success': False, 'error': 'Could not render molecule'}), 400
        
        return jsonify({
            'success': True,
            'image': image_base64
        })
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /molecule/<index>/thumbnail endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': f'Internal error: {error_msg}'}), 500


@app.route('/molecule/<int:index>/3d', methods=['GET'])
def get_molecule_3d(index: int):
    """
    Get 3D coordinates for a molecule.
    
    Response (JSON):
    {
        "success": true,
        "atoms": [{"symbol": "C", "x": 0.0, "y": 0.0, "z": 0.0, "index": 0}, ...],
        "bonds": [{"atom1": 0, "atom2": 1, "order": 1}, ...],
        "smiles": "..."
    }
    """
    try:
        engine = get_engine()
        molecule = engine.get_molecule_by_index(index)
        
        if not molecule.get('smiles'):
            return jsonify({'success': False, 'error': 'Molecule has no SMILES'}), 400
        
        coords = generate_3d_coordinates(molecule['smiles'])
        if coords is None:
            return jsonify({'success': False, 'error': 'Could not generate 3D coordinates'}), 400
        
        return jsonify({
            'success': True,
            **coords
        })
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /molecule/<index>/3d endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': f'Internal error: {error_msg}'}), 500


@app.route('/render', methods=['POST'])
def render_molecule():
    """
    Render a molecule structure image.
    
    Request body (JSON):
    {
        "smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "width": 400,
        "height": 400
    }
    
    Response (JSON):
    {
        "success": true,
        "image": "data:image/png;base64,..."
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        smiles = data.get('smiles')
        if not smiles:
            return jsonify({'success': False, 'error': 'smiles is required'}), 400
        
        width = data.get('width', 400)
        height = data.get('height', 400)
        enhanced = data.get('enhanced', False)
        
        image_base64 = render_molecule_to_base64(smiles, width=width, height=height, enhanced=enhanced)
        if image_base64 is None:
            return jsonify({'success': False, 'error': 'Invalid SMILES string'}), 400
        
        return jsonify({
            'success': True,
            'image': image_base64
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/diseases', methods=['GET'])
def list_diseases():
    """
    List all diseases in the database.
    
    Response (JSON):
    {
        "success": true,
        "diseases": [
            {
                "id": 1,
                "name": "Alzheimer's disease",
                "mesh_id": "D000544",
                "description": null
            },
            ...
        ]
    }
    """
    try:
        engine = get_engine()
        diseases = engine.get_all_diseases()
        
        return jsonify({
            'success': True,
            'diseases': diseases
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /diseases endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/diseases/<disease_name>/molecules', methods=['GET'])
def get_disease_molecules(disease_name: str):
    """
    Get all molecules associated with a disease.
    
    Query parameters:
    - limit (int): Maximum number of molecules to return (default: no limit)
    
    Response (JSON):
    {
        "success": true,
        "disease": "Alzheimer's disease",
        "molecules": [...]
    }
    """
    try:
        limit = request.args.get('limit', None, type=int)
        
        engine = get_engine()
        molecules = engine.get_disease_molecules(disease_name, limit=limit)
        
        return jsonify({
            'success': True,
            'disease': disease_name,
            'molecules': molecules,
            'count': len(molecules)
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /diseases/<disease_name>/molecules endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/diseases/<disease_name>/top-molecules', methods=['GET'])
def get_disease_top_molecules(disease_name: str):
    """
    Get top N molecules for a disease (most commonly used drugs).
    
    Query parameters:
    - top_k (int): Number of top molecules to return (default: 10)
    
    Response (JSON):
    {
        "success": true,
        "disease": "Alzheimer's disease",
        "molecules": [...]
    }
    """
    try:
        top_k = request.args.get('top_k', 10, type=int)
        top_k = min(max(top_k, 1), 100)  # Clamp between 1 and 100
        
        engine = get_engine()
        molecules = engine.get_disease_molecules(disease_name, limit=top_k)
        
        return jsonify({
            'success': True,
            'disease': disease_name,
            'molecules': molecules,
            'count': len(molecules)
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /diseases/<disease_name>/top-molecules endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/search/by-disease', methods=['POST'])
def search_by_disease():
    """
    Search for similar molecules to drugs used for a specific disease.
    
    Request body (JSON):
    {
        "disease_name": "Alzheimer's disease",
        "top_k": 10
    }
    
    Response (JSON):
    {
        "success": true,
        "disease": "Alzheimer's disease",
        "results": [...]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        disease_name = data.get('disease_name')
        if not disease_name:
            return jsonify({'success': False, 'error': 'disease_name is required'}), 400
        
        top_k = data.get('top_k', 10)
        if not isinstance(top_k, int) or top_k < 1:
            top_k = 10
        
        engine = get_engine()
        results = engine.search_by_disease(disease_name, top_k=top_k)
        
        return jsonify({
            'success': True,
            'disease': disease_name,
            'results': results,
            'count': len(results)
        })
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /search/by-disease endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/drugs', methods=['GET'])
def list_drugs():
    """
    List all drugs in the database.
    
    Response (JSON):
    {
        "success": true,
        "drugs": [...]
    }
    """
    try:
        engine = get_engine()
        drugs = engine.get_all_drugs()
        
        return jsonify({
            'success': True,
            'drugs': drugs
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /drugs endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/drugs/<int:drug_id>', methods=['GET'])
def get_drug(drug_id: int):
    """
    Get drug information by ID.
    
    Response (JSON):
    {
        "success": true,
        "drug": {...}
    }
    """
    try:
        engine = get_engine()
        drug = engine.get_drug_by_id(drug_id)
        
        if drug is None:
            return jsonify({
                'success': False,
                'error': f'Drug with ID {drug_id} not found'
            }), 404
        
        return jsonify({
            'success': True,
            'drug': drug
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /drugs/<drug_id> endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/drugs/<int:drug_id>/molecules', methods=['GET'])
def get_drug_molecules(drug_id: int):
    """
    Get active ingredient molecules for a drug.
    
    Response (JSON):
    {
        "success": true,
        "drug": {...},
        "molecules": [...]
    }
    """
    try:
        engine = get_engine()
        drug = engine.get_drug_by_id(drug_id)
        
        if drug is None:
            return jsonify({
                'success': False,
                'error': f'Drug with ID {drug_id} not found'
            }), 404
        
        molecules = engine.get_drug_molecules(drug_id)
        
        return jsonify({
            'success': True,
            'drug': drug,
            'molecules': molecules
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /drugs/<drug_id>/molecules endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/diseases/<disease_name>/drugs', methods=['GET'])
def get_disease_drugs(disease_name: str):
    """
    Get drugs (not just molecules) for a disease.
    
    Query parameters:
    - limit (int): Maximum number of drugs to return (default: no limit)
    
    Response (JSON):
    {
        "success": true,
        "disease": "Alzheimer's disease",
        "drugs": [...],
        "molecules": [...],  // Also include molecules for backward compatibility
        "count": 10
    }
    """
    try:
        limit = request.args.get('limit', None, type=int)
        
        engine = get_engine()
        drugs = engine.get_disease_drugs(disease_name, limit=limit)
        molecules = engine.get_disease_molecules(disease_name, limit=limit)
        
        return jsonify({
            'success': True,
            'disease': disease_name,
            'drugs': drugs,
            'molecules': molecules,  # Include for backward compatibility
            'count': len(drugs)
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /diseases/<disease_name>/drugs endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


def handle_stdin_request():
    """
    Handle a single JSON request from stdin.
    Reads JSON from stdin, processes it, and writes JSON response to stdout.
    
    Input format (JSON):
    {
        "action": "search",
        "query_smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "top_k": 10
    }
    
    Output format (JSON):
    {
        "success": true,
        "results": [...]
    }
    """
    try:
        # Read JSON from stdin
        input_data = json.load(sys.stdin)
        action = input_data.get('action')
        
        if action == 'search':
            query_smiles = input_data.get('query_smiles')
            if not query_smiles:
                raise ValueError('query_smiles is required')
            
            top_k = input_data.get('top_k', 10)
            engine = get_search_engine()
            results = engine.search_similar(query_smiles, top_k=top_k)
            
            response = {
                'success': True,
                'results': results,
                'query_smiles': query_smiles,
                'top_k': len(results)
            }
        
        elif action == 'search_chembl':
            chembl_id = input_data.get('chembl_id')
            if not chembl_id:
                raise ValueError('chembl_id is required')
            
            top_k = input_data.get('top_k', 10)
            engine = get_search_engine()
            results = engine.search_by_chembl_id(chembl_id, top_k=top_k)
            
            response = {
                'success': True,
                'results': results,
                'query_chembl_id': chembl_id,
                'top_k': len(results)
            }
        
        elif action == 'get_molecule':
            index = input_data.get('index')
            if index is None:
                raise ValueError('index is required')
            
            engine = get_search_engine()
            molecule = engine.get_molecule_by_index(index)
            
            response = {
                'success': True,
                'molecule': molecule
            }
        
        else:
            raise ValueError(f'Unknown action: {action}')
        
        # Write JSON response to stdout
        print(json.dumps(response))
        sys.stdout.flush()
    
    except Exception as e:
        error_response = {
            'success': False,
            'error': str(e)
        }
        print(json.dumps(error_response))
        sys.stdout.flush()
        sys.exit(1)


def run_http_server(host: str = '127.0.0.1', port: int = 5000, debug: bool = False):
    """Run the Flask HTTP server."""
    print(f"🚀 Starting BioNeighbor API server on http://{host}:{port}")
    print(f"📖 API endpoints:")
    print(f"   GET  /health - Health check")
    print(f"   POST /search - Search by SMILES")
    print(f"   POST /search/chembl - Search by ChEMBL ID")
    print(f"   POST /search/by-disease - Search similar molecules to disease-related drugs")
    print(f"   GET  /diseases - List all diseases")
    print(f"   GET  /diseases/<name>/molecules - Get molecules for a disease")
    print(f"   GET  /diseases/<name>/drugs - Get drugs for a disease")
    print(f"   GET  /diseases/<name>/top-molecules - Get top molecules for a disease")
    print(f"   GET  /drugs - List all drugs")
    print(f"   GET  /drugs/<drug_id> - Get drug by ID")
    print(f"   GET  /drugs/<drug_id>/molecules - Get active ingredient molecules for a drug")
    print(f"   GET  /molecule/<index> - Get molecule by index")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='BioNeighbor API Server')
    parser.add_argument('--mode', choices=['http', 'stdio'], default='http',
                       help='API mode: http (Flask server) or stdio (stdin/stdout)')
    parser.add_argument('--host', default='127.0.0.1', help='HTTP server host')
    parser.add_argument('--port', type=int, default=5000, help='HTTP server port')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    if args.mode == 'stdio':
        handle_stdin_request()
    else:
        run_http_server(host=args.host, port=args.port, debug=args.debug)

