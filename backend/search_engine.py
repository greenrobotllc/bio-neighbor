"""
Molecular similarity search engine.
Provides search functionality using FAISS index and RDKit fingerprints.
"""

import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors
import pandas as pd

from index_builder import load_index
from fingerprints import compute_morgan_fingerprint, FINGERPRINT_SIZE, RADIUS
from data_loader import get_molecule_by_id, load_from_database
import sqlite3
import json

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
INDEX_PATH = DATA_DIR / "faiss_index.bin"
METADATA_PATH = DATA_DIR / "index_metadata.pkl"
DB_PATH = DATA_DIR / "molecules.db"


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
    
    def _calculate_formula(self, smiles: str) -> Optional[str]:
        """
        Calculate molecular formula from SMILES string.
        
        Args:
            smiles: SMILES string
            
        Returns:
            Molecular formula (e.g., "C9H8O4") or None if invalid
        """
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            formula = rdMolDescriptors.CalcMolFormula(mol)
            return formula
        except Exception as e:
            print(f"⚠️  Warning: Could not calculate formula for {smiles[:50]}: {e}")
            return None
    
    def _get_molecule_info(self, index: int) -> Dict:
        """
        Get molecule information by index.
        
        Args:
            index: Index in the FAISS index
            
        Returns:
            Dictionary with molecule information
        """
        if self.molecule_df is not None:
            # Check if index is within bounds
            if 0 <= index < len(self.molecule_df):
                row = self.molecule_df.iloc[index]
                # Convert all values to Python native types for JSON serialization
                mw = row.get('molecular_weight', 0)
                mw_float = float(mw.item() if hasattr(mw, 'item') else mw) if mw is not None else 0.0
                smiles = str(row.get('smiles', ''))
                # Use stored formula if available, otherwise calculate
                formula = str(row.get('formula', '')) if row.get('formula', '') else (self._calculate_formula(smiles) if smiles else None)
                return {
                    'index': int(index),
                    'chembl_id': str(row.get('chembl_id', '')),
                    'name': str(row.get('name', '')),
                    'smiles': smiles,
                    'molecular_weight': mw_float,
                    'is_approved': bool(row.get('is_approved', False)),
                    'formula': formula,
                    'inchi': str(row.get('inchi', '')),
                    'inchikey': str(row.get('inchikey', '')),
                    'pubchem_cid': str(row.get('pubchem_cid', ''))
                }
        else:
            # Fallback to metadata
            chembl_id = None
            if 'chembl_ids' in self.metadata:
                chembl_ids = self.metadata['chembl_ids']
                if isinstance(chembl_ids, list) and 0 <= index < len(chembl_ids):
                    chembl_id = chembl_ids[index]
            
            return {
                'index': int(index),
                'chembl_id': chembl_id or f'molecule_{index}',
                'name': '',
                'smiles': '',
                'molecular_weight': 0,
                'is_approved': False,
                'formula': None,
                'inchi': '',
                'inchikey': '',
                'pubchem_cid': ''
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
            # Convert NumPy float32 to Python float for JSON serialization
            dist_float = float(dist.item() if hasattr(dist, 'item') else dist)
            molecule_info['similarity_score'] = dist_float
            # Convert distance to similarity (for L2, lower distance = higher similarity)
            # For cosine, distance is already similarity-like
            molecule_info['similarity'] = float(1.0 / (1.0 + dist_float) if dist_float > 0 else 1.0)
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
    
    def list_molecules(self, page: int = 1, per_page: int = 20, search: Optional[str] = None) -> Tuple[List[Dict], Dict]:
        """
        List molecules with pagination and optional name search.
        
        Args:
            page: Page number (1-indexed)
            per_page: Number of molecules per page
            search: Optional search term to filter by name (case-insensitive partial match)
            
        Returns:
            Tuple of (list of molecules, pagination info dict)
        """
        if self.molecule_df is None:
            raise RuntimeError("Molecule database not loaded")
        
        # Filter by search term if provided
        df = self.molecule_df.copy()
        if search:
            search_lower = search.lower()
            # Search in name, chembl_id, and SMILES
            name_match = df['name'].str.lower().str.contains(search_lower, na=False)
            chembl_match = df['chembl_id'].str.lower().str.contains(search_lower, na=False)
            smiles_match = df['smiles'].str.lower().str.contains(search_lower, na=False)
            df = df[name_match | chembl_match | smiles_match]
        
        total = len(df)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        # Validate page number
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # Get molecules for this page
        page_df = df.iloc[start_idx:end_idx]
        
        molecules = []
        for idx, row in page_df.iterrows():
            # Use the original dataframe index, but validate it's within bounds
            original_idx = int(idx)
            if original_idx < 0 or original_idx >= len(self.molecule_df):
                # Skip invalid indices
                continue
            # Convert all values to Python native types for JSON serialization
            mw = row.get('molecular_weight', 0)
            mw_float = float(mw.item() if hasattr(mw, 'item') else mw) if mw is not None else 0.0
            smiles = str(row.get('smiles', ''))
            # Use stored formula if available, otherwise calculate
            formula = str(row.get('formula', '')) if row.get('formula', '') else (self._calculate_formula(smiles) if smiles else None)
            molecule_info = {
                'index': original_idx,
                'chembl_id': str(row.get('chembl_id', '')),
                'name': str(row.get('name', '')),
                'smiles': smiles,
                'molecular_weight': mw_float,
                'is_approved': bool(row.get('is_approved', False)),
                'formula': formula,
                'inchi': str(row.get('inchi', '')),
                'inchikey': str(row.get('inchikey', '')),
                'pubchem_cid': str(row.get('pubchem_cid', ''))
            }
            molecules.append(molecule_info)
        
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages
        }
        
        return molecules, pagination
    
    def get_random_molecules(self, count: int = 20) -> List[Dict]:
        """
        Get a random sample of molecules.
        
        Args:
            count: Number of random molecules to return
            
        Returns:
            List of molecule dictionaries
        """
        if self.molecule_df is None:
            raise RuntimeError("Molecule database not loaded")
        
        # Sample random molecules
        sample_count = min(count, len(self.molecule_df))
        sampled_df = self.molecule_df.sample(n=sample_count, random_state=None)
        
        molecules = []
        for i, (idx, row) in enumerate(sampled_df.iterrows()):
            # Use the actual position in the dataframe as the index
            # Convert all values to Python native types for JSON serialization
            mw = row.get('molecular_weight', 0)
            mw_float = float(mw.item() if hasattr(mw, 'item') else mw) if mw is not None else 0.0
            smiles = str(row.get('smiles', ''))
            # Use stored formula if available, otherwise calculate
            formula = str(row.get('formula', '')) if row.get('formula', '') else (self._calculate_formula(smiles) if smiles else None)
            molecule_info = {
                'index': int(idx),  # Keep original index for random samples
                'chembl_id': str(row.get('chembl_id', '')),
                'name': str(row.get('name', '')),
                'smiles': smiles,
                'molecular_weight': mw_float,
                'is_approved': bool(row.get('is_approved', False)),
                'formula': formula,
                'inchi': str(row.get('inchi', '')),
                'inchikey': str(row.get('inchikey', '')),
                'pubchem_cid': str(row.get('pubchem_cid', ''))
            }
            molecules.append(molecule_info)
        
        return molecules
    
    def get_molecule_with_similar(self, index: int, top_k: int = 10) -> Dict:
        """
        Get molecule information by index along with similar molecules.
        
        Args:
            index: Index in the FAISS index
            top_k: Number of similar molecules to return
            
        Returns:
            Dictionary containing:
            - molecule: The requested molecule
            - similar: List of similar molecules
        """
        # Validate index bounds
        if index < 0 or (self.molecule_df is not None and index >= len(self.molecule_df)):
            raise ValueError(f"Index {index} is out of range. Valid range: 0-{len(self.molecule_df) - 1 if self.molecule_df is not None else self.index.ntotal - 1}")
        
        molecule = self._get_molecule_info(index)
        
        # Get SMILES for similarity search
        if not molecule.get('smiles'):
            # If no SMILES, return molecule without similar
            return {
                'molecule': molecule,
                'similar': []
            }
        
        # Find similar molecules
        try:
            similar = self.search_similar(molecule['smiles'], top_k=top_k + 1)  # +1 to exclude self
            
            # Remove the molecule itself from similar list (it will be first result)
            similar = [m for m in similar if m['index'] != index][:top_k]
        except (ValueError, Exception) as e:
            # If similarity search fails (e.g., invalid SMILES), return empty similar list
            print(f"⚠️  Warning: Could not find similar molecules for index {index}: {e}")
            similar = []
        
        return {
            'molecule': molecule,
            'similar': similar
        }
    
    def get_all_diseases(self) -> List[Dict]:
        """
        Get all diseases in the database.
        
        Returns:
            List of dictionaries with disease information
        """
        if not DB_PATH.exists():
            return []
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT id, name, mesh_id, description FROM diseases ORDER BY name")
            rows = cursor.fetchall()
            
            diseases = []
            for row in rows:
                diseases.append({
                    'id': row[0],
                    'name': row[1],
                    'mesh_id': row[2],
                    'description': row[3]
                })
            
            return diseases
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return []
        finally:
            conn.close()
    
    def get_disease_molecules(self, disease_name: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Get all molecules associated with a disease.
        
        Args:
            disease_name: Name of the disease (case-insensitive partial match)
            limit: Optional limit on number of molecules to return
            
        Returns:
            List of molecule dictionaries
        """
        if not DB_PATH.exists() or self.molecule_df is None:
            return []
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            # Find disease by name (case-insensitive partial match)
            cursor.execute(
                "SELECT id FROM diseases WHERE LOWER(name) LIKE LOWER(?)",
                (f'%{disease_name}%',)
            )
            disease_rows = cursor.fetchall()
            
            if not disease_rows:
                return []
            
            # Get all molecule indices for this disease
            molecule_indices = []
            for disease_row in disease_rows:
                disease_id = disease_row[0]
                cursor.execute(
                    "SELECT molecule_index FROM drug_diseases WHERE disease_id = ?",
                    (disease_id,)
                )
                indices = cursor.fetchall()
                molecule_indices.extend([idx[0] for idx in indices])
            
            # Remove duplicates
            molecule_indices = list(set(molecule_indices))
            
            # Apply limit if specified
            if limit:
                molecule_indices = molecule_indices[:limit]
            
            # Get molecule information
            molecules = []
            for idx in molecule_indices:
                if 0 <= idx < len(self.molecule_df):
                    molecule_info = self._get_molecule_info(int(idx))
                    molecules.append(molecule_info)
            
            return molecules
        
        except sqlite3.OperationalError:
            # Tables don't exist yet
            return []
        finally:
            conn.close()
    
    def search_by_disease(self, disease_name: str, top_k: int = 10) -> List[Dict]:
        """
        Find molecules for a disease, then find similar molecules to those drugs.
        This aggregates similar molecules from all disease-related drugs.
        
        Args:
            disease_name: Name of the disease
            top_k: Number of similar molecules to return per disease drug
            
        Returns:
            List of similar molecules (aggregated and deduplicated)
        """
        # Get molecules for this disease
        disease_molecules = self.get_disease_molecules(disease_name)
        
        if not disease_molecules:
            return []
        
        # For each disease molecule, find similar molecules
        all_similar = []
        seen_indices = set()
        
        for disease_mol in disease_molecules:
            smiles = disease_mol.get('smiles')
            if not smiles:
                continue
            
            try:
                # Find similar molecules
                similar = self.search_similar(smiles, top_k=top_k)
                
                # Add to results (avoid duplicates)
                for mol in similar:
                    mol_idx = mol.get('index')
                    if mol_idx not in seen_indices:
                        all_similar.append(mol)
                        seen_indices.add(mol_idx)
            
            except (ValueError, Exception) as e:
                # Skip if similarity search fails
                continue
        
        # Sort by similarity (higher is better)
        all_similar.sort(key=lambda x: x.get('similarity', 0), reverse=True)
        
        # Return top results
        return all_similar[:top_k * len(disease_molecules)]
    
    def get_disease_drugs(self, disease_name: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Get drugs (not just molecules) associated with a disease.
        
        Args:
            disease_name: Name of the disease (case-insensitive partial match)
            limit: Optional limit on number of drugs to return
            
        Returns:
            List of drug dictionaries
        """
        if not DB_PATH.exists():
            return []
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            # Check if drugs table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='drugs'")
            if not cursor.fetchone():
                return []  # Drugs table doesn't exist yet
            
            # Find disease by name
            cursor.execute(
                "SELECT id FROM diseases WHERE LOWER(name) LIKE LOWER(?)",
                (f'%{disease_name}%',)
            )
            disease_rows = cursor.fetchall()
            
            if not disease_rows:
                return []
            
            # Get drugs for this disease via drug_diseases table
            drug_ids = []
            for disease_row in disease_rows:
                disease_id = disease_row[0]
                cursor.execute(
                    "SELECT DISTINCT drug_id FROM drug_diseases WHERE disease_id = ? AND drug_id IS NOT NULL",
                    (disease_id,)
                )
                ids = cursor.fetchall()
                drug_ids.extend([id[0] for id in ids])
            
            # Remove duplicates
            drug_ids = list(set(drug_ids))
            
            if not drug_ids:
                return []
            
            # Apply limit if specified
            if limit:
                drug_ids = drug_ids[:limit]
            
            # Get drug information
            placeholders = ','.join(['?'] * len(drug_ids))
            cursor.execute(
                f"SELECT * FROM drugs WHERE id IN ({placeholders})",
                drug_ids
            )
            rows = cursor.fetchall()
            
            # Get column names
            columns = [description[0] for description in cursor.description]
            
            drugs = []
            for row in rows:
                drug_dict = dict(zip(columns, row))
                # Parse JSON fields
                if drug_dict.get('brand_names'):
                    try:
                        drug_dict['brand_names'] = json.loads(drug_dict['brand_names'])
                    except:
                        drug_dict['brand_names'] = []
                if drug_dict.get('active_ingredients'):
                    try:
                        active_ingredients = json.loads(drug_dict['active_ingredients'])
                        # Convert to list of molecule indices
                        if isinstance(active_ingredients, list):
                            indices = []
                            for item in active_ingredients:
                                if isinstance(item, dict):
                                    indices.append(item.get('molecule_index', item.get('index')))
                                else:
                                    indices.append(item)
                            drug_dict['active_ingredient_molecule_indices'] = indices
                        else:
                            drug_dict['active_ingredient_molecule_indices'] = []
                    except:
                        drug_dict['active_ingredient_molecule_indices'] = []
                else:
                    drug_dict['active_ingredient_molecule_indices'] = []
                if drug_dict.get('inactive_ingredients'):
                    try:
                        drug_dict['inactive_ingredients'] = json.loads(drug_dict['inactive_ingredients'])
                    except:
                        drug_dict['inactive_ingredients'] = []
                else:
                    drug_dict['inactive_ingredients'] = []
                drugs.append(drug_dict)
            
            return drugs
        
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
    
    def get_drug_by_id(self, drug_id: int) -> Optional[Dict]:
        """
        Get drug information by ID.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            Dictionary with drug information or None if not found
        """
        if not DB_PATH.exists():
            return None
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM drugs WHERE id = ?", (drug_id,))
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            columns = [description[0] for description in cursor.description]
            drug_dict = dict(zip(columns, row))
            
            # Parse JSON fields
            if drug_dict.get('brand_names'):
                try:
                    drug_dict['brand_names'] = json.loads(drug_dict['brand_names'])
                except:
                    drug_dict['brand_names'] = []
            if drug_dict.get('active_ingredients'):
                try:
                    active_ingredients = json.loads(drug_dict['active_ingredients'])
                    # Convert to list of molecule indices
                    if isinstance(active_ingredients, list):
                        indices = []
                        for item in active_ingredients:
                            if isinstance(item, dict):
                                indices.append(item.get('molecule_index', item.get('index')))
                            else:
                                indices.append(item)
                        drug_dict['active_ingredient_molecule_indices'] = indices
                    else:
                        drug_dict['active_ingredient_molecule_indices'] = []
                except:
                    drug_dict['active_ingredient_molecule_indices'] = []
            else:
                drug_dict['active_ingredient_molecule_indices'] = []
            if drug_dict.get('inactive_ingredients'):
                try:
                    drug_dict['inactive_ingredients'] = json.loads(drug_dict['inactive_ingredients'])
                except:
                    drug_dict['inactive_ingredients'] = []
            else:
                drug_dict['inactive_ingredients'] = []
            
            return drug_dict
        
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
    
    def get_drug_molecules(self, drug_id: int) -> List[Dict]:
        """
        Get active ingredient molecules for a drug.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            List of molecule dictionaries
        """
        drug = self.get_drug_by_id(drug_id)
        if not drug:
            return []
        
        # Get active ingredient molecule indices
        active_indices = drug.get('active_ingredient_molecule_indices', [])
        if not active_indices:
            # Try old field name for backward compatibility
            active_indices = drug.get('active_ingredients', [])
            if isinstance(active_indices, str):
                try:
                    active_indices = json.loads(active_indices)
                except:
                    return []
        
        if not active_indices:
            return []
        
        # Get molecule information for each index
        molecules = []
        for idx in active_indices:
            if isinstance(idx, dict):
                idx = idx.get('molecule_index', idx.get('index'))
            if idx is not None and 0 <= idx < len(self.molecule_df) if self.molecule_df is not None else False:
                molecule_info = self._get_molecule_info(int(idx))
                molecules.append(molecule_info)
        
        return molecules
    
    def get_all_drugs(self) -> List[Dict]:
        """
        Get all drugs in the database.
        
        Returns:
            List of drug dictionaries
        """
        if not DB_PATH.exists():
            return []
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='drugs'")
            if not cursor.fetchone():
                return []
            
            cursor.execute("SELECT * FROM drugs ORDER BY name")
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            
            drugs = []
            for row in rows:
                drug_dict = dict(zip(columns, row))
                # Parse JSON fields
                if drug_dict.get('brand_names'):
                    try:
                        drug_dict['brand_names'] = json.loads(drug_dict['brand_names'])
                    except:
                        drug_dict['brand_names'] = []
                if drug_dict.get('active_ingredients'):
                    try:
                        active_ingredients = json.loads(drug_dict['active_ingredients'])
                        # Convert to list of molecule indices
                        if isinstance(active_ingredients, list):
                            indices = []
                            for item in active_ingredients:
                                if isinstance(item, dict):
                                    indices.append(item.get('molecule_index', item.get('index')))
                                else:
                                    indices.append(item)
                            drug_dict['active_ingredient_molecule_indices'] = indices
                        else:
                            drug_dict['active_ingredient_molecule_indices'] = []
                    except:
                        drug_dict['active_ingredient_molecule_indices'] = []
                else:
                    drug_dict['active_ingredient_molecule_indices'] = []
                if drug_dict.get('inactive_ingredients'):
                    try:
                        drug_dict['inactive_ingredients'] = json.loads(drug_dict['inactive_ingredients'])
                    except:
                        drug_dict['inactive_ingredients'] = []
                else:
                    drug_dict['inactive_ingredients'] = []
                drugs.append(drug_dict)
            
            return drugs
        
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()


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

