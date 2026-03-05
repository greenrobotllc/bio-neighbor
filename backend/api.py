"""
API interface for BioNeighbor search engine.
Provides JSON-based API via HTTP (Flask) or stdin/stdout.
"""

import json
import logging
import sys
import os
import re
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS

logger = logging.getLogger(__name__)

from search_engine import SearchEngine, get_search_engine
from molecule_renderer import render_molecule_to_base64, generate_3d_coordinates
try:
    from bond_analysis import extract_atom_bond_data, compute_mcs, identify_functional_groups, compare_molecules
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from bond_analysis import extract_atom_bond_data, compute_mcs, identify_functional_groups, compare_molecules

# Compiled regex for validating names in download endpoints
ALLOWED_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 \-_\(\),\.']+$")
# Stricter pattern for comma-joined names (no spaces/commas) to avoid injection when joining
ALLOWED_COMPACT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
# Allow a restricted, human-friendly disease string (letters, numbers, spaces, ()-_,.' and comma)
ALLOWED_DISEASE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-_\(\),\.']{0,199}$")
# Detect control characters that should never be accepted in user input
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")

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


def validate_disease_input(value: Any) -> Optional[str]:
    """
    Validate disease input before it is passed to subprocess commands.
    Returns an error message when invalid, otherwise None.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return 'disease must be a string'
    cleaned = value.strip()
    if not cleaned:
        return 'disease cannot be empty'
    if len(cleaned) > 200:
        return 'Disease name too long (max 200 chars)'
    if CONTROL_CHAR_PATTERN.search(cleaned):
        return 'Disease contains invalid control characters'
    if not ALLOWED_DISEASE_PATTERN.match(cleaned):
        return "Invalid characters detected in disease. Allowed: letters, numbers, spaces, (), -, _, comma, period, apostrophe."
    return None


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
        
        # Validate SMILES length to prevent DoS (engine.search_similar will validate format)
        if len(query_smiles) > 1000:
            return jsonify({
                'success': False, 
                'error': 'SMILES string too long (max 1000 characters)'
            }), 400
        
        engine = get_engine()
        # search_similar() will validate SMILES format and raise ValueError if invalid
        results = engine.search_similar(query_smiles, top_k=top_k)
        
        return jsonify({
            'success': True,
            'results': results,
            'query_smiles': query_smiles,
            'top_k': len(results)
        })
    
    except ValueError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /search endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except OSError as e:
        # Handle broken pipe and other OS errors
        return jsonify({
            'success': False, 
            'error': f'Backend error: {str(e)}. Please ensure the search engine is properly initialized.'
        }), 500
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /search endpoint")
        return jsonify({
            'success': False, 
            'error': 'Internal server error'
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
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /search/chembl endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /search/chembl endpoint")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


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
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /molecules endpoint")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
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
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /molecule endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /molecule endpoint")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


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
        # Clamp dimensions to prevent DoS (thumbnail should be small)
        width = min(max(width, 16), 512)
        height = min(max(height, 16), 512)
        
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
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /molecule/<index>/thumbnail endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /molecule/<index>/thumbnail endpoint")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


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
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /molecule/<index>/3d endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /molecule/<index>/3d endpoint")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@app.route('/molecule/<int:index>/bonds', methods=['GET'])
def get_molecule_bonds(index: int):
    """
    Get detailed atom and bond data for a molecule.
    
    Response (JSON):
    {
        "success": true,
        "atoms": [
            {
                "index": 0,
                "symbol": "C",
                "atomic_num": 6,
                "formal_charge": 0,
                "hybridization": "SP3",
                "is_aromatic": false,
                ...
            },
            ...
        ],
        "bonds": [
            {
                "atom1": 0,
                "atom2": 1,
                "order": 1,
                "is_aromatic": false,
                "is_in_ring": false,
                ...
            },
            ...
        ],
        "smiles": "..."
    }
    """
    try:
        engine = get_engine()
        molecule = engine.get_molecule_by_index(index)
        
        if not molecule.get('smiles'):
            return jsonify({'success': False, 'error': 'Molecule has no SMILES'}), 400
        
        bond_data = extract_atom_bond_data(molecule['smiles'])
        if bond_data is None:
            return jsonify({'success': False, 'error': 'Could not extract bond data'}), 400
        
        return jsonify({
            'success': True,
            **bond_data
        })
    
    except ValueError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /molecule/<index>/bonds endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /molecule/<index>/bonds endpoint")
        return jsonify({'success': False, 'error': 'Internal error processing bond data'}), 500


@app.route('/molecule/<int:index>/functional-groups', methods=['GET'])
def get_molecule_functional_groups(index: int):
    """
    Get functional groups identified in a molecule.
    
    Response (JSON):
    {
        "success": true,
        "functional_groups": [
            {
                "type": "hydroxyl",
                "atoms": [5, 6],
                "description": "Hydroxyl group (-OH)"
            },
            ...
        ],
        "smiles": "..."
    }
    """
    try:
        engine = get_engine()
        molecule = engine.get_molecule_by_index(index)
        
        if not molecule.get('smiles'):
            return jsonify({'success': False, 'error': 'Molecule has no SMILES'}), 400
        
        functional_groups = identify_functional_groups(molecule['smiles'])
        
        return jsonify({
            'success': True,
            'functional_groups': functional_groups,
            'smiles': molecule['smiles']
        })
    
    except ValueError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /molecule/<index>/functional-groups endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /molecule/<index>/functional-groups endpoint")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@app.route('/molecules/compare', methods=['POST'])
def compare_molecules_endpoint():
    """
    Compare two molecules and return MCS and differences.
    
    Request body (JSON):
    {
        "smiles1": "CC(=O)Oc1ccccc1C(=O)O",
        "smiles2": "CC(=O)Nc1ccc(O)cc1",
        "index1": 0,  // Optional: molecule index for first molecule
        "index2": 1   // Optional: molecule index for second molecule
    }
    
    Response (JSON):
    {
        "success": true,
        "molecule1": {
            "atoms": [...],
            "bonds": [...],
            "smiles": "..."
        },
        "molecule2": {
            "atoms": [...],
            "bonds": [...],
            "smiles": "..."
        },
        "mcs": {
            "mcs_smiles": "...",
            "num_atoms": 5,
            "num_bonds": 4,
            "shared_atoms_1": [0, 1, 2, ...],
            "shared_atoms_2": [0, 1, 2, ...],
            "shared_bonds_1": [0, 1, ...],
            "shared_bonds_2": [0, 1, ...],
            ...
        },
        "functional_groups_1": [...],
        "functional_groups_2": [...]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        # Get SMILES from request or from molecule indices
        smiles1 = data.get('smiles1')
        smiles2 = data.get('smiles2')
        index1 = data.get('index1')
        index2 = data.get('index2')
        
        # If indices provided, get SMILES from database
        if index1 is not None:
            engine = get_engine()
            mol1 = engine.get_molecule_by_index(index1)
            if not mol1.get('smiles'):
                return jsonify({'success': False, 'error': f'Molecule at index {index1} has no SMILES'}), 400
            smiles1 = mol1['smiles']
        
        if index2 is not None:
            engine = get_engine()
            mol2 = engine.get_molecule_by_index(index2)
            if not mol2.get('smiles'):
                return jsonify({'success': False, 'error': f'Molecule at index {index2} has no SMILES'}), 400
            smiles2 = mol2['smiles']
        
        if not smiles1 or not smiles2:
            return jsonify({'success': False, 'error': 'smiles1 and smiles2 (or index1 and index2) are required'}), 400
        
        # Validate SMILES length
        if len(smiles1) > 1000 or len(smiles2) > 1000:
            return jsonify({
                'success': False,
                'error': 'SMILES strings too long (max 1000 characters each)'
            }), 400
        
        # Compare molecules
        comparison = compare_molecules(smiles1, smiles2)
        if comparison is None:
            return jsonify({'success': False, 'error': 'Could not compare molecules'}), 400
        
        return jsonify({
            'success': True,
            **comparison
        })
    
    except ValueError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"ValueError in /molecules/compare endpoint: {str(e)}")
        return jsonify({'success': False, 'error': 'Invalid request parameters'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /molecules/compare endpoint")
        return jsonify({'success': False, 'error': 'Internal error processing molecule comparison'}), 500


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
        
        # Validate width/height - return 400 for invalid inputs
        try:
            width = int(data.get('width', 400))
            height = int(data.get('height', 400))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'width and height must be integers'}), 400
        
        # Clamp dimensions to prevent DoS (larger limit for render endpoint)
        width = min(max(width, 16), 2048)
        height = min(max(height, 16), 2048)
        enhanced = data.get('enhanced', False)
        
        image_base64 = render_molecule_to_base64(smiles, width=width, height=height, enhanced=enhanced)
        if image_base64 is None:
            return jsonify({'success': False, 'error': 'Invalid SMILES string'}), 400
        
        return jsonify({
            'success': True,
            'image': image_base64
        })
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /render endpoint")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


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
        
        # Validate disease name length
        if isinstance(disease_name, str) and len(disease_name) > 200:
            return jsonify({
                'success': False,
                'error': 'Disease name too long (max 200 chars)'
            }), 400
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
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("ValueError in /search/by-disease endpoint: %s", str(e))
        return jsonify({'success': False, 'error': 'Invalid input parameter'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in /search/by-disease endpoint")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@app.route('/download/status/<task_id>', methods=['GET'])
def get_download_status(task_id: str):
    """
    Get status of a download task with detailed progress.
    
    Response (JSON):
    {
        "success": true,
        "running": true/false,
        "exit_code": null or int,
        "message": "...",
        "progress": {
            "status": "searching|loading|saving|completed",
            "details": {...}
        }
    }
    """
    try:
        import os
        from progress_tracker import read_progress
        from task_registry import get_task_info
        
        # Resolve UUID to PID via registry
        task_info = get_task_info(task_id)
        if not task_info:
            return jsonify({
                'success': False,
                'error': 'Task not found'
            }), 404
        
        pid = task_info['pid']
        
        # Read progress from file (using UUID, not PID)
        progress_data = read_progress(task_id)
        
        # Try psutil first (more reliable)
        try:
            import psutil
            try:
                process = psutil.Process(pid)
                is_running = process.is_running()
                
                if is_running:
                    # Process is running - return progress if available
                    message = progress_data.get('message', 'Download in progress') if progress_data else 'Download in progress'
                    return jsonify({
                        'success': True,
                        'running': True,
                        'exit_code': None,
                        'message': message,
                        'progress': progress_data
                    })
                else:
                    # Process finished - need to wait() to get returncode
                    # psutil.Process.returncode is only populated after wait() or wait_procs()
                    try:
                        process.wait(timeout=0.1)  # Non-blocking wait
                        exit_code = process.returncode
                    except (psutil.TimeoutExpired, AttributeError):
                        # Fallback: check progress file for exit code
                        exit_code = progress_data.get('exit_code') if progress_data else None
                    
                    message = 'Download completed' if exit_code == 0 else 'Download failed'
                    if progress_data:
                        message = progress_data.get('message', message)
                    
                    return jsonify({
                        'success': True,
                        'running': False,
                        'exit_code': exit_code,
                        'message': message,
                        'progress': progress_data
                    })
            except psutil.NoSuchProcess:
                # Process finished - check progress file for final status
                message = 'Process completed' if progress_data and progress_data.get('status') == 'completed' else 'Process not found (may have completed)'
                return jsonify({
                    'success': True,
                    'running': False,
                    'exit_code': 0 if progress_data and progress_data.get('status') == 'completed' else None,
                    'message': message,
                    'progress': progress_data
                })
        except ImportError:
            # psutil not available, use basic os.kill check
            pass
        
        # Fallback: use os.kill to check if process exists
        try:
            # Signal 0 doesn't kill, just checks if process exists
            os.kill(pid, 0)
            message = progress_data.get('message', 'Download in progress') if progress_data else 'Download in progress'
            return jsonify({
                'success': True,
                'running': True,
                'exit_code': None,
                'message': message,
                'progress': progress_data
            })
        except ProcessLookupError:
            # Process doesn't exist - check progress file
            message = 'Process completed' if progress_data and progress_data.get('status') == 'completed' else 'Process not found (may have completed)'
            return jsonify({
                'success': True,
                'running': False,
                'exit_code': 0 if progress_data and progress_data.get('status') == 'completed' else None,
                'message': message,
                'progress': progress_data
            })
        except PermissionError:
            # Process exists but we can't access it (likely finished)
            message = progress_data.get('message', 'Process status unknown') if progress_data else 'Process status unknown'
            return jsonify({
                'success': True,
                'running': False,
                'exit_code': None,
                'message': message,
                'progress': progress_data
            })
        except OSError:
            message = progress_data.get('message', 'Process not found') if progress_data else 'Process not found'
            return jsonify({
                'success': True,
                'running': False,
                'exit_code': None,
                'message': message,
                'progress': progress_data
            })
    
    except Exception as e:
        import traceback
        print(f"❌ Error checking download status: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Error checking status: {str(e)}'
        }), 500


@app.route('/stats', methods=['GET'])
def get_stats():
    """
    Get database statistics.
    
    Response (JSON):
    {
        "success": true,
        "stats": {
            "molecules": 10000,
            "drugs": 150,
            "diseases": 50,
            "relationships": 200
        }
    }
    """
    try:
        engine = get_engine()
        stats = engine.get_database_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /stats endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/search/molecules', methods=['GET'])
def search_molecules():
    """
    Search molecules by name for autocomplete.
    
    Query parameters:
    - q (string): Search query
    - limit (int): Maximum results (default: 20)
    
    Response (JSON):
    {
        "success": true,
        "results": [...]
    }
    """
    try:
        query = request.args.get('q', '', type=str)
        limit = request.args.get('limit', 20, type=int)
        limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
        
        engine = get_engine()
        results = engine.search_molecules_by_name(query, limit=limit)
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /search/molecules endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/search/drugs', methods=['GET'])
def search_drugs():
    """
    Search drugs by name for autocomplete.
    
    Query parameters:
    - q (string): Search query
    - limit (int): Maximum results (default: 20)
    
    Response (JSON):
    {
        "success": true,
        "results": [...]
    }
    """
    try:
        query = request.args.get('q', '', type=str)
        limit = request.args.get('limit', 20, type=int)
        limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
        
        engine = get_engine()
        results = engine.search_drugs_by_name(query, limit=limit)
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /search/drugs endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/search/diseases', methods=['GET'])
def search_diseases():
    """
    Search diseases by name for autocomplete.
    
    Query parameters:
    - q (string): Search query
    - limit (int): Maximum results (default: 20)
    
    Response (JSON):
    {
        "success": true,
        "results": [...]
    }
    """
    try:
        query = request.args.get('q', '', type=str)
        limit = request.args.get('limit', 20, type=int)
        limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
        
        engine = get_engine()
        results = engine.search_diseases_by_name(query, limit=limit)
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /search/diseases endpoint: {error_msg}")
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


@app.route('/download/molecules', methods=['POST'])
def download_molecules():
    """
    Download molecules by count or name.
    
    Request body (JSON):
    {
        "count": 1000,  // Optional: number of molecules to download
        "source": "pubchem",  // Optional: "pubchem", "chembl", "zinc"
        "names": ["aspirin", "ibuprofen"]  // Optional: list of molecule names
    }
    
    Response (JSON):
    {
        "success": true,
        "message": "Download started",
        "task_id": "..."
    }
    """
    try:
        data = request.get_json() or {}
        count = data.get('count')
        source = data.get('source', 'pubchem')
        names = data.get('names', [])
        full_file = data.get('full_file', False)

        # Validate source from allowlist (already present)
        if source not in {'pubchem', 'chembl', 'zinc'}:
            return jsonify({
                'success': False,
                'error': 'Invalid source. Must be one of: pubchem, chembl, zinc'
            }), 400

        # Validate and clamp count
        MAX_COUNT = 1000
        try:
            count_int = int(count) if count is not None else None
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Parameter "count" must be an integer.'
            }), 400
        if count_int is not None:
            if not (1 <= count_int <= MAX_COUNT):
                return jsonify({
                    'success': False,
                    'error': f'Parameter "count" must be between 1 and {MAX_COUNT}.'
                }), 400
        count = count_int  # Use the validated int value from now on

        # Validate names: must be a list of allowed names (alphanumeric/underscore)
        if names:
            if not isinstance(names, list):
                return jsonify({
                    'success': False,
                    'error': 'Parameter "names" must be a list.'
                }), 400
            if len(names) > 200:
                return jsonify({
                    'success': False,
                    'error': 'Too many names (max 200)'
                }), 400
            for n in names:
                if not isinstance(n, str):
                    return jsonify({
                        'success': False,
                        'error': 'All entries in "names" must be strings.'
                    }), 400
                if len(n) > 200:
                    return jsonify({
                        'success': False,
                        'error': 'Name too long (max 200 chars)'
                    }), 400
                if not ALLOWED_COMPACT_NAME_PATTERN.match(n):
                    return jsonify({
                        'success': False,
                        'error': 'Invalid entry in "names". Only alphanumeric, underscores, and hyphens allowed.'
                    }), 400
        if not count and not names and not full_file:
            return jsonify({
                'success': False,
                'error': 'Either count, names, or full_file must be provided'
            }), 400
        
        # Build command
        import subprocess
        import sys
        import os
        from pathlib import Path
        
        script_path = Path(__file__).parent / "download_molecules.py"
        
        # Validate script exists
        if not script_path.exists():
            return jsonify({
                'success': False,
                'error': f'Download script not found: {script_path}'
            }), 500
        
        # Use venv Python if available
        venv_python = Path(__file__).parent.parent / "venv" / "bin" / "python"
        python_exec = str(venv_python) if venv_python.exists() else sys.executable
        
        if names:
            # Download by names
            names_str = ','.join(names)
            cmd = [python_exec, str(script_path), '--names', names_str]
        elif full_file:
            # Download full SDF file
            cmd = [python_exec, str(script_path), '--full-file', '--source', source]
        else:
            # Download by count
            cmd = [python_exec, str(script_path), '--count', str(count), '--source', source]
        
        # Validate command
        print(f"🔍 Running download command: {' '.join(cmd)}")
        
        # Generate UUID task_id BEFORE starting process so it can be passed to script
        import uuid
        from task_registry import register_task
        task_id = str(uuid.uuid4())
        
        # Run in background with proper environment
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['BIO_NEIGHBOR_TASK_ID'] = task_id  # Pass task_id to subprocess
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=str(Path(__file__).parent),
                bufsize=1  # Line buffered
            )
            
            # Register task with actual PID and pre-generated task_id
            register_task(process.pid, cmd, task_type="download_molecules", task_id=task_id)
            
            # Check if process started successfully
            if process.poll() is not None:
                # Process already finished (likely an error)
                stdout, stderr = process.communicate()
                error_msg = stderr or stdout or "Process failed immediately"
                print(f"❌ Download process failed: {error_msg}")
                return jsonify({
                    'success': False,
                    'error': f'Download failed: {error_msg[:200]}'
                }), 500
            
            print(f"✅ Download process started with PID: {process.pid}, Task ID: {task_id}")
            print(f"📊 Streaming output in real-time...")
            
            # Stream output in background thread
            from stream_process_output import stream_output
            stream_output(process, log_callback=lambda msg: print(msg))
            
            # Start a daemon thread to wait for process and update final status
            import threading
            def process_reaper():
                try:
                    process.wait()  # Wait for process to complete
                    # Update progress file with final status
                    from progress_tracker import write_progress
                    exit_code = process.returncode
                    if exit_code == 0:
                        write_progress(task_id, 'completed', 'Download completed successfully', {})
                    else:
                        write_progress(task_id, 'failed', f'Download failed with exit code {exit_code}', {'exit_code': exit_code})
                except Exception as e:
                    print(f"⚠️  Error in process reaper: {e}")
            
            reaper_thread = threading.Thread(target=process_reaper, daemon=True)
            reaper_thread.start()
            
            return jsonify({
                'success': True,
                'message': 'Download started',
                'task_id': task_id
            })
        
        except Exception as e:
            print(f"❌ Error starting download process: {e}")
            return jsonify({
                'success': False,
                'error': f'Failed to start download: {str(e)}'
            }), 500
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /download/molecules endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/download/drugs', methods=['POST'])
def download_drugs():
    """
    Download drugs by name, disease, or bulk download.
    
    Request body (JSON):
    {
        "names": ["donepezil", "rivastigmine"],  // Optional: list of drug names
        "disease": "Alzheimer's disease",  // Optional: disease name
        "count": 10,  // Optional: number of drugs per disease or max drugs for bulk
        "bulk": true  // Optional: bulk download common drugs (ignores names/disease)
    }
    
    Response (JSON):
    {
        "success": true,
        "message": "Download started",
        "task_id": "..."
    }
    """
    try:
        data = request.get_json() or {}
        names = data.get('names', [])
        disease = data.get('disease')
        count = data.get('count', 10)
        bulk = data.get('bulk', False)
        
        # Validate inputs
        # Validate and clamp count
        if count is not None:
            if not isinstance(count, int):
                return jsonify({'success': False, 'error': 'count must be an integer'}), 400
            count = min(max(count, 1), 100000)  # Clamp to reasonable max
        
        # Validate names
        if names:
            if not isinstance(names, list):
                return jsonify({'success': False, 'error': 'names must be a list'}), 400
            if len(names) > 200:
                return jsonify({
                    'success': False,
                    'error': 'Too many names (max 200)'
                }), 400
            if not all(isinstance(n, str) for n in names):
                return jsonify({'success': False, 'error': 'names must be a list of strings'}), 400
            if any(len(n) > 200 for n in names):
                return jsonify({
                    'success': False,
                    'error': 'Name too long (max 200 chars)'
                }), 400
            # Additional validation: allow only safe characters in names
            for n in names:
                if not ALLOWED_NAME_PATTERN.match(n):
                    return jsonify({
                        'success': False,
                        'error': f"Invalid characters detected in name: '{n}'. Allowed: letters, numbers, spaces, (), -, _, comma, period, apostrophe."
                    }), 400
        disease_error = validate_disease_input(disease)
        if disease_error:
            return jsonify({'success': False, 'error': disease_error}), 400
        if isinstance(disease, str):
            disease = disease.strip()
        
        if not names and not disease and not bulk:
            return jsonify({
                'success': False,
                'error': 'Either names, disease, or bulk must be provided'
            }), 400
        
        import subprocess
        import sys
        import os
        from pathlib import Path
        
        # Use venv Python if available
        venv_python = Path(__file__).parent.parent / "venv" / "bin" / "python"
        python_exec = str(venv_python) if venv_python.exists() else sys.executable
        
        if bulk:
            # Bulk download drugs - use RxNorm for 1000+ drugs (better for drug-specific data)
            # RxNorm API: https://lhncbc.nlm.nih.gov/RxNav/APIs/index.html
            if count and count >= 1000:
                script_path = Path(__file__).parent / "download_drugs_rxnorm.py"
                if script_path.exists():
                    cmd = [python_exec, str(script_path), '--max-drugs', str(count)]
                else:
                    # Fallback to PubChem bulk download
                    script_path = Path(__file__).parent / "download_drugs_bulk.py"
                    cmd = [python_exec, str(script_path), '--max-drugs', str(count), '--use-cid-search']
            else:
                # For smaller downloads, use PubChem bulk (faster for < 1000)
                script_path = Path(__file__).parent / "download_drugs_bulk.py"
                cmd = [python_exec, str(script_path)]
                if count:
                    cmd.extend(['--max-drugs', str(count)])
            
            if not script_path.exists():
                return jsonify({
                    'success': False,
                    'error': f'Bulk download script not found: {script_path}'
                }), 500
        elif names:
            # Download by names
            script_path = Path(__file__).parent / "download_by_name.py"
            if not script_path.exists():
                return jsonify({
                    'success': False,
                    'error': f'Download script not found: {script_path}'
                }), 500
            names_str = ','.join(names)
            cmd = [python_exec, str(script_path), 'drugs', '--names', names_str]
        else:
            # Download by disease - use download_by_name.py for single disease downloads
            # This uses PubChem to search for drugs by disease indication
            script_path = Path(__file__).parent / "download_by_name.py"
            if not script_path.exists():
                return jsonify({
                    'success': False,
                    'error': f'Download script not found: {script_path}'
                }), 500
            
            # Use download_by_name.py to download drugs for a specific disease
            # This script uses PubChem API to search for drugs by disease indication
            cmd = [python_exec, str(script_path), 'diseases', '--names', disease, '--max-drugs', str(count)]
        
        print(f"🔍 Running download command: {' '.join(cmd)}")
        
        # Generate UUID task_id BEFORE starting process so it can be passed to script
        import uuid
        from task_registry import register_task
        task_id = str(uuid.uuid4())
        
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['BIO_NEIGHBOR_TASK_ID'] = task_id  # Pass task_id to subprocess
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=str(Path(__file__).parent),
                bufsize=1  # Line buffered
            )
            
            # Register task with actual PID and pre-generated task_id
            register_task(process.pid, cmd, task_type="download_drugs", task_id=task_id)
            
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                error_msg = stderr or stdout or "Process failed immediately"
                print(f"❌ Download process failed: {error_msg}")
                return jsonify({
                    'success': False,
                    'error': f'Download failed: {error_msg[:200]}'
                }), 500
            
            print(f"✅ Download process started with PID: {process.pid}, Task ID: {task_id}")
            print(f"📊 Streaming output in real-time...")
            
            # Stream output in background thread
            from stream_process_output import stream_output
            stream_output(process, log_callback=lambda msg: print(msg))
            
            # Start a daemon thread to wait for process and update final status
            import threading
            def process_reaper():
                try:
                    process.wait()  # Wait for process to complete
                    # Update progress file with final status
                    from progress_tracker import write_progress
                    exit_code = process.returncode
                    if exit_code == 0:
                        write_progress(task_id, 'completed', 'Download completed successfully', {})
                    else:
                        write_progress(task_id, 'failed', f'Download failed with exit code {exit_code}', {'exit_code': exit_code})
                except Exception as e:
                    print(f"⚠️  Error in process reaper: {e}")
            
            reaper_thread = threading.Thread(target=process_reaper, daemon=True)
            reaper_thread.start()
            
            return jsonify({
                'success': True,
                'message': 'Download started',
                'task_id': task_id
            })
        
        except Exception as e:
            print(f"❌ Error starting download process: {e}")
            return jsonify({
                'success': False,
                'error': f'Failed to start download: {str(e)}'
            }), 500
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /download/drugs endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


@app.route('/download/diseases', methods=['POST'])
def download_diseases():
    """
    Download diseases by name or bulk.
    
    For bulk downloads, uses NLM Clinical Tables API which provides 2,400+ medical conditions
    with ICD-10-CM and ICD-9-CM codes.
    
    Request body (JSON):
    {
        "names": ["Alzheimer's disease", "diabetes"],  // Optional: list of disease names
        "count": 100  // Optional: number of diseases to download (bulk uses NLM API)
    }
    
    Response (JSON):
    {
        "success": true,
        "message": "Download started",
        "task_id": "..."
    }
    
    References:
    - NLM Clinical Tables API: https://clinicaltables.nlm.nih.gov/apidoc/conditions/v3/doc.html
    """
    try:
        data = request.get_json() or {}
        names = data.get('names', [])
        count = data.get('count')
        
        # Validate inputs
        # Validate and clamp count
        if count is not None:
            if not isinstance(count, int):
                return jsonify({'success': False, 'error': 'count must be an integer'}), 400
            count = min(max(count, 1), 100000)  # Clamp to reasonable max
        
        # Validate names
        if names:
            if not isinstance(names, list):
                return jsonify({'success': False, 'error': 'names must be a list'}), 400
            if len(names) > 200:
                return jsonify({
                    'success': False,
                    'error': 'Too many names (max 200)'
                }), 400
            if not all(isinstance(n, str) for n in names):
                return jsonify({'success': False, 'error': 'names must be a list of strings'}), 400
            if any(len(n) > 200 for n in names):
                return jsonify({
                    'success': False,
                    'error': 'Name too long (max 200 chars)'
                }), 400
            # Additional validation: allow only safe characters in names
            for n in names:
                if not ALLOWED_NAME_PATTERN.match(n):
                    return jsonify({
                        'success': False,
                        'error': f"Invalid characters detected in name: '{n}'. Allowed: letters, numbers, spaces, (), -, _, comma, period, apostrophe."
                    }), 400
        
        if not names and count is None:
            # If no names and no count, download all diseases from NLM
            count = None  # Will download all from NLM dataset
        
        import subprocess
        import sys
        import os
        from pathlib import Path
        
        # Use venv Python if available
        venv_python = Path(__file__).parent.parent / "venv" / "bin" / "python"
        python_exec = str(venv_python) if venv_python.exists() else sys.executable
        
        if names:
            # Download by names
            script_path = Path(__file__).parent / "download_by_name.py"
            if not script_path.exists():
                return jsonify({
                    'success': False,
                    'error': f'Download script not found: {script_path}'
                }), 500
            names_str = ','.join(names)
            cmd = [python_exec, str(script_path), 'diseases', '--names', names_str]
        else:
            # Bulk download - use NLM Clinical Tables for comprehensive disease data
            # NLM provides 2,400+ medical conditions with ICD codes
            # If count is None, download all diseases from the dataset
            script_path = Path(__file__).parent / "download_diseases_nlm.py"
            if script_path.exists():
                cmd = [python_exec, str(script_path), '--use-download']
                if count:
                    cmd.extend(['--max-diseases', str(count)])
            else:
                # Fallback to top 100 diseases
                script_path = Path(__file__).parent / "download_disease_drugs.py"
                if not script_path.exists():
                    return jsonify({
                        'success': False,
                        'error': f'Download script not found: {script_path}'
                    }), 500
                cmd = [python_exec, str(script_path), '--top-100', '--max-diseases', str(count)]
        
        print(f"🔍 Running download command: {' '.join(cmd)}")
        
        # Generate UUID task_id BEFORE starting process so it can be passed to script
        import uuid
        from task_registry import register_task
        task_id = str(uuid.uuid4())
        
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['BIO_NEIGHBOR_TASK_ID'] = task_id  # Pass task_id to subprocess
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=str(Path(__file__).parent),
                bufsize=1  # Line buffered
            )
            
            # Register task with actual PID and pre-generated task_id
            register_task(process.pid, cmd, task_type="download_diseases", task_id=task_id)
            
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                error_msg = stderr or stdout or "Process failed immediately"
                print(f"❌ Download process failed: {error_msg}")
                return jsonify({
                    'success': False,
                    'error': f'Download failed: {error_msg[:200]}'
                }), 500
            
            print(f"✅ Download process started with PID: {process.pid}, Task ID: {task_id}")
            print(f"📊 Streaming output in real-time...")
            
            # Stream output in background thread
            from stream_process_output import stream_output
            stream_output(process, log_callback=lambda msg: print(msg))
            
            # Start a daemon thread to wait for process and update final status
            import threading
            def process_reaper():
                try:
                    process.wait()  # Wait for process to complete
                    # Update progress file with final status
                    from progress_tracker import write_progress
                    exit_code = process.returncode
                    if exit_code == 0:
                        write_progress(task_id, 'completed', 'Download completed successfully', {})
                    else:
                        write_progress(task_id, 'failed', f'Download failed with exit code {exit_code}', {'exit_code': exit_code})
                except Exception as e:
                    print(f"⚠️  Error in process reaper: {e}")
            
            reaper_thread = threading.Thread(target=process_reaper, daemon=True)
            reaper_thread.start()
            
            return jsonify({
                'success': True,
                'message': 'Download started',
                'task_id': task_id
            })
        
        except Exception as e:
            print(f"❌ Error starting download process: {e}")
            return jsonify({
                'success': False,
                'error': f'Failed to start download: {str(e)}'
            }), 500
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Unexpected error in /download/diseases endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal error: {error_msg}'
        }), 500


# Cancer Research API Endpoints

@app.route('/cancer-research/mechanisms', methods=['GET'])
def list_mechanisms():
    """
    List all mechanisms.

    Response (JSON):
    {
        "success": true,
        "mechanisms": [...]
    }

    If no mechanisms exist, returns an empty list. Use POST /cancer-research/mechanisms/initialize
    to initialize default mechanisms.
    """
    try:
        # Ensure database schema is up to date
        from db_migrations import migrate_database
        migrate_database()

        from cancer_mechanism_loader import get_all_mechanisms

        mechanisms = get_all_mechanisms()

        return jsonify({
            'success': True,
            'mechanisms': mechanisms,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/initialize', methods=['POST'])
def initialize_mechanisms():
    """
    Initialize all default mechanisms (adenosine and PD-1/PD-L1) and related data.
    Automatically triggers ETL to load targets, ligands, assays, and outcomes.
    
    Response (JSON):
    {
        "success": true,
        "message": "Mechanisms initialized",
        "mechanism_ids": [1, 2],
        "data_loaded": {
            "mechanism_1": {
                "targets_loaded": 4,
                "ligands_loaded": 45,
                "assays_loaded": 12,
                "outcomes_loaded": 5,
                "cancer_mappings_loaded": 6
            }
        }
    }
    """
    try:
        from cancer_mechanism_loader import load_all_default_mechanisms
        from target_loader import get_targets_for_mechanism
        from ligand_loader import get_ligands_for_mechanism
        from assay_loader import get_assays_for_mechanism
        from drug_outcome_loader import get_drug_outcomes_for_mechanism
        from cancer_mapping_loader import get_cancers_for_mechanism
        
        # Load all default mechanisms with ETL (ETL is triggered automatically)
        mechanism_ids = load_all_default_mechanisms(load_data=True)
        if not mechanism_ids:
            return jsonify({
                'success': False,
                'error': 'Failed to load mechanisms'
            }), 500
        
        # Collect detailed data counts for each mechanism
        data_loaded = {}
        for mechanism_id in mechanism_ids:
            try:
                # Get counts of loaded data
                targets = get_targets_for_mechanism(mechanism_id)
                ligands = get_ligands_for_mechanism(mechanism_id)
                assays = get_assays_for_mechanism(mechanism_id)
                outcomes = get_drug_outcomes_for_mechanism(mechanism_id)
                cancer_mappings = get_cancers_for_mechanism(mechanism_id)
                
                data_loaded[f'mechanism_{mechanism_id}'] = {
                    'targets_loaded': len(targets),
                    'ligands_loaded': len(ligands),
                    'assays_loaded': len(assays),
                    'outcomes_loaded': len(outcomes),
                    'cancer_mappings_loaded': len(cancer_mappings)
                }
            except Exception as e:
                data_loaded[f'mechanism_{mechanism_id}'] = {
                    'error': 'Failed to load data counts'
                }
        
        return jsonify({
            'success': True,
            'message': f'Initialized {len(mechanism_ids)} mechanisms successfully',
            'mechanism_ids': mechanism_ids,
            'data_loaded': data_loaded
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/<int:mechanism_id>/load-data', methods=['POST'])
def load_mechanism_data_endpoint(mechanism_id: int):
    """
    Manually trigger ETL to load/refresh all data for a mechanism.
    
    Request body (JSON, optional):
    {
        "force_refresh": false
    }
    
    Response (JSON):
    {
        "success": true,
        "mechanism_id": 1,
        "targets_loaded": 4,
        "ligands_loaded": 45,
        "assays_loaded": 12,
        "outcomes_loaded": 5,
        "cancer_mappings_loaded": 6,
        "errors": [],
        "warnings": []
    }
    """
    try:
        from cancer_research_etl import load_mechanism_data
        
        # Get force_refresh from request body
        force_refresh = False
        if request.is_json:
            data = request.get_json()
            force_refresh = data.get('force_refresh', False)
        
        # Run ETL
        result = load_mechanism_data(mechanism_id, force_refresh=force_refresh)
        
        return jsonify({
            'success': True,
            **result
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/<int:mechanism_id>', methods=['GET'])
def get_mechanism(mechanism_id: int):
    """
    Get mechanism details.
    
    Response (JSON):
    {
        "success": true,
        "mechanism": {...}
    }
    """
    try:
        from cancer_mechanism_loader import get_mechanism_by_id
        mechanism = get_mechanism_by_id(mechanism_id)
        
        if not mechanism:
            return jsonify({
                'success': False,
                'error': f'Mechanism {mechanism_id} not found'
            }), 404
        
        return jsonify({
            'success': True,
            'mechanism': mechanism,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/<int:mechanism_id>/targets', methods=['GET'])
def get_mechanism_targets(mechanism_id: int):
    """
    Get targets for a mechanism.
    
    Response (JSON):
    {
        "success": true,
        "targets": [...]
    }
    """
    try:
        from target_loader import get_targets_for_mechanism
        targets = get_targets_for_mechanism(mechanism_id)
        
        return jsonify({
            'success': True,
            'targets': targets,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/targets/<int:target_id>', methods=['GET'])
def get_target(target_id: int):
    """
    Get target details.
    
    Response (JSON):
    {
        "success": true,
        "target": {...}
    }
    """
    try:
        from target_loader import get_target_by_id
        target = get_target_by_id(target_id)
        
        if not target:
            return jsonify({
                'success': False,
                'error': f'Target {target_id} not found'
            }), 404
        
        return jsonify({
            'success': True,
            'target': target,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/targets/<int:target_id>/ligands', methods=['GET'])
def get_target_ligands(target_id: int):
    """
    Get ligands for a target.
    
    Response (JSON):
    {
        "success": true,
        "ligands": [...]
    }
    """
    try:
        from ligand_loader import get_ligands_for_target
        ligands = get_ligands_for_target(target_id)
        
        return jsonify({
            'success': True,
            'ligands': ligands,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/<int:mechanism_id>/ligands', methods=['GET'])
def get_mechanism_ligands(mechanism_id: int):
    """
    Get all ligands for a mechanism.
    
    Response (JSON):
    {
        "success": true,
        "ligands": [...]
    }
    """
    try:
        from ligand_loader import get_ligands_for_mechanism
        ligands = get_ligands_for_mechanism(mechanism_id)
        
        # Log the actual count for debugging
        ligand_count = len(ligands) if ligands else 0
        print(f"📊 API: get_mechanism_ligands({mechanism_id}) returned {ligand_count} ligands")
        
        if ligand_count == 0:
            print(f"⚠️  Warning: No ligands found for mechanism {mechanism_id}")
        
        return jsonify({
            'success': True,
            'ligands': ligands or [],
            'count': ligand_count,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/<int:mechanism_id>/drug-outcomes', methods=['GET'])
def get_mechanism_drug_outcomes(mechanism_id: int):
    """
    Get drug outcomes for a mechanism.
    
    Response (JSON):
    {
        "success": true,
        "outcomes": [...]
    }
    """
    try:
        from drug_outcome_loader import get_drug_outcomes_for_mechanism
        outcomes = get_drug_outcomes_for_mechanism(mechanism_id)
        
        # Log the actual count for debugging
        outcome_count = len(outcomes) if outcomes else 0
        print(f"📊 API: get_mechanism_drug_outcomes({mechanism_id}) returned {outcome_count} outcomes")
        
        if outcome_count == 0:
            print(f"⚠️  Warning: No outcomes found for mechanism {mechanism_id}")
        
        return jsonify({
            'success': True,
            'outcomes': outcomes or [],
            'count': outcome_count,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/<int:mechanism_id>/assays', methods=['GET'])
def get_mechanism_assays(mechanism_id: int):
    """
    Get assays for a mechanism.
    
    Response (JSON):
    {
        "success": true,
        "assays": [...]
    }
    """
    try:
        from assay_loader import get_assays_for_mechanism
        assays = get_assays_for_mechanism(mechanism_id)
        
        # Log the actual count for debugging
        assay_count = len(assays) if assays else 0
        print(f"📊 API: get_mechanism_assays({mechanism_id}) returned {assay_count} assays")
        
        if assay_count == 0:
            print(f"⚠️  Warning: No assays found for mechanism {mechanism_id}")
        
        return jsonify({
            'success': True,
            'assays': assays or [],
            'count': assay_count,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/debug/mechanisms/<int:mechanism_id>/counts', methods=['GET'])
def get_mechanism_data_counts(mechanism_id: int):
    """
    Debug endpoint to check actual data counts in database.
    
    Response (JSON):
    {
        "success": true,
        "mechanism_id": 1,
        "targets_count": 4,
        "ligands_count": 45,
        "assays_count": 12,
        "outcomes_count": 8,
        "raw_queries": {
            "targets": "SELECT COUNT(*) FROM targets t JOIN mechanism_targets mt...",
            "ligands": "SELECT COUNT(*) FROM ligands l JOIN targets t...",
            "assays": "SELECT COUNT(*) FROM assays a JOIN targets t...",
            "outcomes": "SELECT COUNT(*) FROM drug_outcomes do..."
        }
    }
    """
    try:
        import sqlite3
        from data_loader import DB_PATH
        
        if not DB_PATH.exists():
            return jsonify({
                'success': False,
                'error': 'Database not found'
            }), 404
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Count targets
        cursor.execute("""
            SELECT COUNT(DISTINCT t.id)
            FROM targets t
            JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ?
        """, (mechanism_id,))
        targets_count = cursor.fetchone()[0]
        
        # Count ligands (through targets)
        cursor.execute("""
            SELECT COUNT(DISTINCT l.id)
            FROM ligands l
            JOIN targets t ON l.target_id = t.id
            JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ?
        """, (mechanism_id,))
        ligands_count = cursor.fetchone()[0]
        
        # Count assays (through targets)
        cursor.execute("""
            SELECT COUNT(DISTINCT a.id)
            FROM assays a
            JOIN targets t ON a.target_id = t.id
            JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ?
        """, (mechanism_id,))
        assays_count = cursor.fetchone()[0]
        
        # Count outcomes (through ligands -> targets)
        cursor.execute("""
            SELECT COUNT(DISTINCT do.id)
            FROM drug_outcomes do
            LEFT JOIN ligands l ON do.molecule_index = l.molecule_index
            LEFT JOIN targets t ON l.target_id = t.id
            LEFT JOIN mechanism_targets mt ON t.id = mt.target_id
            WHERE mt.mechanism_id = ?
        """, (mechanism_id,))
        outcomes_count = cursor.fetchone()[0]
        
        # Also check total counts in tables (for debugging)
        cursor.execute("SELECT COUNT(*) FROM ligands")
        total_ligands = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM assays")
        total_assays = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM drug_outcomes")
        total_outcomes = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'mechanism_id': mechanism_id,
            'targets_count': targets_count,
            'ligands_count': ligands_count,
            'assays_count': assays_count,
            'outcomes_count': outcomes_count,
            'debug': {
                'total_ligands_in_db': total_ligands,
                'total_assays_in_db': total_assays,
                'total_outcomes_in_db': total_outcomes
            }
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/health/data-sources', methods=['GET'])
def check_data_sources():
    """
    Check availability of external data sources.
    
    Response (JSON):
    {
        "chembl": {"available": true/false, "response_time_ms": 123},
        "pubchem": {"available": true/false, "response_time_ms": 456},
        "bindingdb": {"available": true/false},
        "iuphar": {"available": true/false}
    }
    """
    import time
    import requests
    
    results = {}
    
    # Test ChEMBL
    try:
        from ligand_loader import test_chembl_connectivity, CHEMBL_AVAILABLE
        if CHEMBL_AVAILABLE:
            start_time = time.time()
            available = test_chembl_connectivity()
            response_time = (time.time() - start_time) * 1000
            results['chembl'] = {
                'available': available,
                'response_time_ms': round(response_time, 0) if available else None
            }
        else:
            results['chembl'] = {'available': False, 'error': 'Package not installed'}
    except Exception as e:
        results['chembl'] = {'available': False, 'error': str(e)}
    
    # Test PubChem
    try:
        from ligand_loader import PUBCHEM_AVAILABLE
        if PUBCHEM_AVAILABLE:
            start_time = time.time()
            try:
                import pubchempy as pcp
                # Try a simple query
                compound = pcp.get_compounds('aspirin', 'name', as_dataframe=True)
                response_time = (time.time() - start_time) * 1000
                results['pubchem'] = {
                    'available': compound is not None and len(compound) > 0,
                    'response_time_ms': round(response_time, 0)
                }
            except Exception as e:
                results['pubchem'] = {'available': False, 'error': str(e)}
        else:
            results['pubchem'] = {'available': False, 'error': 'Package not installed'}
    except Exception as e:
        results['pubchem'] = {'available': False, 'error': str(e)}
    
    # Test BindingDB
    try:
        start_time = time.time()
        response = requests.get('https://bindingdb.org/api/v1/targets?uniprot=P21589', timeout=5)
        response_time = (time.time() - start_time) * 1000
        results['bindingdb'] = {
            'available': response.status_code == 200,
            'response_time_ms': round(response_time, 0) if response.status_code == 200 else None,
            'status_code': response.status_code
        }
    except requests.exceptions.RequestException as e:
        results['bindingdb'] = {'available': False, 'error': str(e)}
    except Exception as e:
        results['bindingdb'] = {'available': False, 'error': str(e)}
    
    # Test IUPHAR
    try:
        start_time = time.time()
        response = requests.get('https://www.guidetopharmacology.org/services/targets.json', timeout=10)
        response_time = (time.time() - start_time) * 1000
        results['iuphar'] = {
            'available': response.status_code == 200,
            'response_time_ms': round(response_time, 0) if response.status_code == 200 else None,
            'status_code': response.status_code
        }
    except requests.exceptions.RequestException as e:
        results['iuphar'] = {'available': False, 'error': str(e)}
    except Exception as e:
        results['iuphar'] = {'available': False, 'error': str(e)}
    
    return jsonify({
        'success': True,
        'data_sources': results,
        'timestamp': time.time()
    })


@app.route('/cancer-research/cancers', methods=['GET'])
def list_cancers():
    """
    List all cancer types with mechanism activity.
    
    Response (JSON):
    {
        "success": true,
        "cancers": [...]
    }
    """
    try:
        from cancer_mapping_loader import get_all_cancer_types
        cancers = get_all_cancer_types()
        
        return jsonify({
            'success': True,
            'cancers': cancers,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/cancers/<cancer_type>/mechanisms', methods=['GET'])
def get_cancer_mechanisms(cancer_type: str):
    """
    Get mechanisms for a cancer type.
    
    Response (JSON):
    {
        "success": true,
        "mechanisms": [...]
    }
    """
    try:
        from cancer_mapping_loader import get_mechanisms_for_cancer
        mechanisms = get_mechanisms_for_cancer(cancer_type)
        
        return jsonify({
            'success': True,
            'cancer_type': cancer_type,
            'mechanisms': mechanisms,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/mechanisms/<int:mechanism_id>/cancers', methods=['GET'])
def get_mechanism_cancers(mechanism_id: int):
    """
    Get cancer types associated with a mechanism.
    
    Response (JSON):
    {
        "success": true,
        "cancers": [...]
    }
    """
    try:
        from cancer_mapping_loader import get_cancers_for_mechanism
        mappings = get_cancers_for_mechanism(mechanism_id)
        
        return jsonify({
            'success': True,
            'mechanism_id': mechanism_id,
            'cancers': mappings,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/workspaces', methods=['GET'])
def list_workspaces():
    """
    List all workspaces.
    
    Response (JSON):
    {
        "success": true,
        "workspaces": [...]
    }
    """
    try:
        import sqlite3
        from data_loader import DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workspaces ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        
        columns = [d[0] for d in cursor.description]
        workspaces = [dict(zip(columns, row)) for row in rows]
        
        # Parse JSON fields
        for workspace in workspaces:
            for field in ['filters', 'selections']:
                if workspace.get(field):
                    try:
                        workspace[field] = json.loads(workspace[field])
                    except (json.JSONDecodeError, TypeError):
                        workspace[field] = {}
        
        conn.close()
        
        return jsonify({
            'success': True,
            'workspaces': workspaces
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/workspaces/<int:workspace_id>', methods=['GET'])
def get_workspace(workspace_id: int):
    """
    Get workspace state.
    
    Response (JSON):
    {
        "success": true,
        "workspace": {...}
    }
    """
    try:
        import sqlite3
        from data_loader import DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({
                'success': False,
                'error': f'Workspace {workspace_id} not found'
            }), 404
        
        columns = [d[0] for d in cursor.description]
        workspace = dict(zip(columns, row))
        
        # Parse JSON fields
        for field in ['filters', 'selections']:
            if workspace.get(field):
                try:
                    workspace[field] = json.loads(workspace[field])
                except (json.JSONDecodeError, TypeError):
                    workspace[field] = {}
        
        return jsonify({
            'success': True,
            'workspace': workspace
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/workspaces', methods=['POST'])
def create_workspace():
    """
    Create a new workspace.
    
    Request body (JSON):
    {
        "mechanism_id": 1,
        "filters": {...},
        "selections": {...},
        "notes": "..."
    }
    
    Response (JSON):
    {
        "success": true,
        "workspace_id": 1
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        mechanism_id = data.get('mechanism_id')
        filters = data.get('filters', {})
        selections = data.get('selections', {})
        notes = data.get('notes', '')
        
        import sqlite3
        from data_loader import DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO workspaces (mechanism_id, filters, selections, notes)
            VALUES (?, ?, ?, ?)
        """, (
            mechanism_id,
            json.dumps(filters),
            json.dumps(selections),
            notes
        ))
        workspace_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/workspaces/<int:workspace_id>', methods=['PUT'])
def update_workspace(workspace_id: int):
    """
    Update workspace state.
    
    Request body (JSON):
    {
        "filters": {...},
        "selections": {...},
        "notes": "..."
    }
    
    Response (JSON):
    {
        "success": true
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        import sqlite3
        from data_loader import DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Build update query with parameterized fields
        fields_to_update = []
        values = []

        if 'filters' in data:
            fields_to_update.append("filters = ?")
            values.append(json.dumps(data['filters']))

        if 'selections' in data:
            fields_to_update.append("selections = ?")
            values.append(json.dumps(data['selections']))

        if 'notes' in data:
            fields_to_update.append("notes = ?")
            values.append(data['notes'])

        if not fields_to_update:
            conn.close()
            return jsonify({'success': False, 'error': 'No fields to update'}), 400

        fields_to_update.append("updated_at = CURRENT_TIMESTAMP")
        values.append(workspace_id)

        sql = "UPDATE workspaces SET " + ", ".join(fields_to_update) + " WHERE id = ?"
        cursor.execute(sql, values)
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Workspace {workspace_id} not found'
            }), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/workspaces/<int:workspace_id>', methods=['DELETE'])
def delete_workspace(workspace_id: int):
    """
    Delete a workspace.
    
    Response (JSON):
    {
        "success": true
    }
    """
    try:
        import sqlite3
        from data_loader import DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Workspace {workspace_id} not found'
            }), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
        }), 500


@app.route('/cancer-research/similarity/ligands', methods=['POST'])
def find_similar_ligands():
    """
    Find similar ligands across mechanisms.
    
    Request body (JSON):
    {
        "ligand_id": 1,
        "top_k": 10
    }
    
    Response (JSON):
    {
        "success": true,
        "similar_ligands": [...]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        ligand_id = data.get('ligand_id')
        top_k = data.get('top_k', 10)
        
        # Use existing similarity search engine
        engine = get_engine()
        
        # Get ligand SMILES
        import sqlite3
        from data_loader import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT smiles FROM ligands WHERE id = ?", (ligand_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result or not result[0]:
            return jsonify({
                'success': False,
                'error': f'Ligand {ligand_id} not found or has no SMILES'
            }), 404
        
        # Search for similar molecules
        results = engine.search_similar(result[0], top_k=top_k)
        
        return jsonify({
            'success': True,
            'similar_ligands': results,
            'disclaimer': 'Research tool only - not for medical diagnosis or treatment'
        })
    except Exception as e:
        logger.exception("Cancer research endpoint error")
        return jsonify({
            'success': False,
            'error': 'An internal error occurred'
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
            
            # Use same validation as HTTP endpoint
            if len(query_smiles) > 1000:
                raise ValueError('SMILES string too long (max 1000 characters)')
            
            top_k = input_data.get('top_k', 10)
            # Validate and clamp top_k
            if not isinstance(top_k, int):
                top_k = 10
            top_k = min(max(top_k, 1), 100)  # Clamp to reasonable range
            
            # Use get_engine() for consistency with HTTP endpoints
            engine = get_engine()
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
            # Validate and clamp top_k
            if not isinstance(top_k, int):
                top_k = 10
            top_k = min(max(top_k, 1), 100)  # Clamp to reasonable range
            
            # Use get_engine() for consistency with HTTP endpoints
            engine = get_engine()
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
            
            # Validate index is an integer
            if not isinstance(index, int):
                try:
                    index = int(index)
                except (ValueError, TypeError):
                    raise ValueError('index must be an integer')
            
            # Use get_engine() for consistency with HTTP endpoints
            engine = get_engine()
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
        # Sanitize error message
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        error_response = {
            'success': False,
            'error': error_msg
        }
        print(json.dumps(error_response))
        sys.stdout.flush()
        sys.exit(1)


def run_http_server(host: str = '127.0.0.1', port: int = 5000, debug: bool = False):
    """Run the Flask HTTP server."""
    # Only enable debug mode if explicitly requested via environment variable
    # This prevents accidental exposure of Werkzeug debugger
    debug_enabled = debug and os.environ.get('BIO_NEIGHBOR_DEBUG') == '1'
    if debug and not debug_enabled:
        print("⚠️  Debug mode requested but BIO_NEIGHBOR_DEBUG=1 not set. Use env var to enable.")
        debug_enabled = False
    
    # Force bind to localhost when debug is enabled for security
    if debug_enabled:
        host = '127.0.0.1'
    
    print("🚀 Starting BioNeighbor API server on http://{host}:{port}".format(host=host, port=port))
    print("📖 API endpoints:")
    print("   GET  /health - Health check")
    print("   POST /search - Search by SMILES")
    print("   POST /search/chembl - Search by ChEMBL ID")
    print("   POST /search/by-disease - Search similar molecules to disease-related drugs")
    print("   GET  /diseases - List all diseases")
    print("   GET  /diseases/<name>/molecules - Get molecules for a disease")
    print("   GET  /diseases/<name>/drugs - Get drugs for a disease")
    print("   GET  /diseases/<name>/top-molecules - Get top molecules for a disease")
    print("   GET  /drugs - List all drugs")
    print("   GET  /drugs/<drug_id> - Get drug by ID")
    print("   GET  /drugs/<drug_id>/molecules - Get active ingredient molecules for a drug")
    print("   GET  /molecule/<index> - Get molecule by index")
    print("   GET  /cancer-research/mechanisms - List all mechanisms")
    print("   GET  /cancer-research/mechanisms/<id> - Get mechanism details")
    print("   GET  /cancer-research/mechanisms/<id>/targets - Get targets for mechanism")
    print("   GET  /cancer-research/mechanisms/<id>/ligands - Get ligands for mechanism")
    print("   GET  /cancer-research/mechanisms/<id>/assays - Get assays for mechanism")
    print("   GET  /cancer-research/mechanisms/<id>/drug-outcomes - Get drug outcomes")
    print("   GET  /cancer-research/cancers - List cancer types")
    print("   GET  /cancer-research/workspaces - List workspaces")
    print("   POST /cancer-research/workspaces - Create workspace")
    print("   PUT  /cancer-research/workspaces/<id> - Update workspace")
    app.run(host=host, port=port, debug=debug_enabled)


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

