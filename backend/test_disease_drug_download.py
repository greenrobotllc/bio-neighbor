"""
Tests for disease-drug download functionality.
Tests the multi-API loader, download_by_name script, and API endpoints.
"""

import unittest
import sqlite3
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from data_loader import DB_PATH
from download_by_name import download_diseases
from multi_api_disease_loader import search_drugs_by_disease_multi_api
from db_migrations import migrate_database


class TestDiseaseDrugDownload(unittest.TestCase):
    """Test disease-drug download functionality."""
    
    def setUp(self):
        """Set up test database."""
        # Create temporary database
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db_path = Path(self.test_db.name)
        self.test_db.close()
        
        # Backup original DB_PATH
        self.original_db_path = DB_PATH
        
        # Patch DB_PATH to use test database
        import data_loader
        data_loader.DB_PATH = self.test_db_path
        
        # Initialize schema in test database
        migrate_database()
        
        # Create molecules table (needed for tests)
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS molecules (
                rowid INTEGER PRIMARY KEY,
                smiles TEXT NOT NULL,
                name TEXT,
                molecular_weight REAL,
                pubchem_cid TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up test database."""
        # Restore original DB_PATH
        import data_loader
        data_loader.DB_PATH = self.original_db_path
        
        # Remove test database
        if self.test_db_path.exists():
            self.test_db_path.unlink()
    
    def test_multi_api_loader_available(self):
        """Test that multi-API loader can be imported."""
        try:
            from multi_api_disease_loader import search_drugs_by_disease_multi_api
            self.assertTrue(callable(search_drugs_by_disease_multi_api))
        except ImportError as e:
            self.skipTest(f"Multi-API loader not available: {e}")
    
    @patch('multi_api_disease_loader.openfda_search')
    @patch('multi_api_disease_loader.clinicaltrials_search')
    @patch('multi_api_disease_loader.pubchem_search')
    def test_multi_api_loader_fallback(self, mock_pubchem, mock_clinicaltrials, mock_openfda):
        """Test that multi-API loader falls back through APIs."""
        # Mock openFDA to return some drugs
        mock_openfda.return_value = [
            {'name': 'Test Drug 1', 'generic_name': 'Test Generic 1', 'api_source': 'openfda'},
            {'name': 'Test Drug 2', 'generic_name': 'Test Generic 2', 'api_source': 'openfda'},
        ]
        
        # Mock ClinicalTrials to return more drugs
        mock_clinicaltrials.return_value = [
            {'name': 'Trial Drug 1', 'api_source': 'clinicaltrials'},
        ]
        
        # Mock PubChem to return even more
        mock_pubchem.return_value = [
            {'name': 'PubChem Drug 1', 'api_source': 'pubchem'},
        ]
        
        # Test with openFDA available
        with patch('multi_api_disease_loader.OPENFDA_AVAILABLE', True):
            with patch('multi_api_disease_loader.CLINICALTRIALS_AVAILABLE', True):
                with patch('multi_api_disease_loader.PUBCHEM_AVAILABLE', True):
                    drugs = search_drugs_by_disease_multi_api("test disease", max_drugs=10)
                    
                    # Should get drugs from all sources
                    self.assertGreater(len(drugs), 0)
                    
                    # Check that openFDA drugs are included
                    openfda_drugs = [d for d in drugs if d.get('api_source') == 'openfda']
                    self.assertGreater(len(openfda_drugs), 0)
                    
                    # Verify API calls were made
                    mock_openfda.assert_called_once()
    
    def test_download_diseases_creates_relationships(self):
        """Test that download_diseases creates disease-drug relationships."""
        # Create some test molecules in database
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        
        # Insert a test molecule
        cursor.execute("""
            INSERT INTO molecules (smiles, name, molecular_weight, pubchem_cid)
            VALUES (?, ?, ?, ?)
        """, ("CCO", "Ethanol", 46.07, "702"))
        conn.commit()
        conn.close()
        
        # Mock the multi-API search to return test drugs
        with patch('download_by_name.search_drugs_by_disease_multi_api') as mock_search:
            mock_search.return_value = [
                {
                    'name': 'Test Drug',
                    'generic_name': 'Test Generic',
                    'pubchem_cid': '702',  # Matches our test molecule
                    'smiles': 'CCO',
                    'molecular_weight': 46.07,
                    'api_source': 'openfda',
                    'indication': 'Test indication',
                }
            ]
            
            # Mock load_drug_info to return drug info
            with patch('download_by_name.load_drug_info') as mock_load:
                mock_load.return_value = {
                    'name': 'Test Drug',
                    'pubchem_cid': '702',
                    'smiles': 'CCO',
                    'molecular_weight': 46.07,
                    'molecule_index': 1,  # Matches our inserted molecule
                }
                
                # Download diseases
                count = download_diseases(["Test Disease"], max_drugs_per_disease=1)
                
                # Should have processed 1 disease
                self.assertEqual(count, 1)
                
                # Verify disease was created
                conn = sqlite3.connect(self.test_db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM diseases WHERE name = ?", ("Test Disease",))
                disease_row = cursor.fetchone()
                self.assertIsNotNone(disease_row, "Disease should be created")
                
                # Verify relationship was created
                if disease_row:
                    disease_id = disease_row[0]
                    cursor.execute("""
                        SELECT COUNT(*) FROM drug_diseases WHERE disease_id = ?
                    """, (disease_id,))
                    count = cursor.fetchone()[0]
                    self.assertGreater(count, 0, "Should have created disease-drug relationship")
                
                conn.close()
    
    def test_download_diseases_handles_no_molecule_match(self):
        """Test that download_diseases handles drugs without molecule matches."""
        # Mock the multi-API search
        with patch('download_by_name.search_drugs_by_disease_multi_api') as mock_search:
            mock_search.return_value = [
                {
                    'name': 'Unmatched Drug',
                    'generic_name': 'Unmatched Generic',
                    'pubchem_cid': '999999',
                    'smiles': 'CCCC',
                    'molecular_weight': 58.12,
                    'api_source': 'openfda',
                }
            ]
            
            # Mock load_drug_info to return None (no match)
            with patch('download_by_name.load_drug_info') as mock_load:
                mock_load.return_value = None
                
                # Mock fetch_drug_details_from_pubchem (it's in pubchem_drug_loader)
                with patch('pubchem_drug_loader.fetch_drug_details_from_pubchem') as mock_fetch:
                    mock_fetch.return_value = {
                        'name': 'Unmatched Drug',
                        'pubchem_cid': '999999',
                        'smiles': 'CCCC',
                    }
                    
                    # Download should not crash
                    count = download_diseases(["Test Disease 2"], max_drugs_per_disease=1)
                    
                    # Should have processed the disease
                    self.assertEqual(count, 1)
    
    def test_download_diseases_deduplicates(self):
        """Test that download_diseases doesn't create duplicate relationships."""
        # Create test molecule
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO molecules (smiles, name, molecular_weight, pubchem_cid)
            VALUES (?, ?, ?, ?)
        """, ("CCO", "Ethanol", 46.07, "702"))
        conn.commit()
        conn.close()
        
        # Mock search to return same drug twice
        with patch('download_by_name.search_drugs_by_disease_multi_api') as mock_search:
            mock_search.return_value = [
                {
                    'name': 'Test Drug',
                    'pubchem_cid': '702',
                    'smiles': 'CCO',
                    'api_source': 'openfda',
                },
                {
                    'name': 'Test Drug',
                    'pubchem_cid': '702',
                    'smiles': 'CCO',
                    'api_source': 'clinicaltrials',  # Same drug from different source
                }
            ]
            
            with patch('download_by_name.load_drug_info') as mock_load:
                mock_load.return_value = {
                    'name': 'Test Drug',
                    'pubchem_cid': '702',
                    'smiles': 'CCO',
                    'molecule_index': 1,
                }
                
                # Download twice
                download_diseases(["Test Disease"], max_drugs_per_disease=2)
                download_diseases(["Test Disease"], max_drugs_per_disease=2)
                
                # Verify only one relationship exists
                conn = sqlite3.connect(self.test_db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM diseases WHERE name = ?", ("Test Disease",))
                disease_row = cursor.fetchone()
                if disease_row:
                    disease_id = disease_row[0]
                    cursor.execute("""
                        SELECT COUNT(*) FROM drug_diseases WHERE disease_id = ?
                    """, (disease_id,))
                    count = cursor.fetchone()[0]
                    # Should have only 1 relationship (not 2)
                    self.assertEqual(count, 1, "Should not create duplicate relationships")
                conn.close()


class TestDiseaseDrugDownloadAPI(unittest.TestCase):
    """Test disease-drug download API endpoints."""
    
    def setUp(self):
        """Set up test Flask app."""
        from api import app
        self.app = app.test_client()
        self.app.testing = True
    
    def test_download_drugs_by_disease_endpoint(self):
        """Test POST /download/drugs with disease parameter."""
        # Mock the subprocess to avoid actually running the script
        import subprocess
        with patch('subprocess.Popen') as mock_popen:
            # Mock process
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None  # Still running
            mock_popen.return_value = mock_process
            
            # Make request
            response = self.app.post('/download/drugs', json={
                'disease': 'AIDS',
                'count': 10
            })
            
            # Should return success
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data.get('success'))
            self.assertIn('task_id', data)
            
            # Verify correct script was called
            call_args = mock_popen.call_args[0][0]
            self.assertIn('download_by_name.py', ' '.join(call_args))
            self.assertIn('diseases', call_args)
            self.assertIn('--names', call_args)
            self.assertIn('AIDS', ' '.join(call_args))
    
    def test_download_drugs_by_disease_validation(self):
        """Test that disease download requires disease parameter."""
        response = self.app.post('/download/drugs', json={})
        
        # Should return error
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get('success'))
        self.assertIn('error', data)
    
    def test_download_drugs_by_disease_uses_correct_script(self):
        """Test that disease download uses download_by_name.py, not download_disease_drugs.py."""
        import subprocess
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process
            
            response = self.app.post('/download/drugs', json={
                'disease': 'Schizophrenia',
                'count': 20
            })
            
            self.assertEqual(response.status_code, 200)
            
            # Verify it's using download_by_name.py, not download_disease_drugs.py
            call_args = ' '.join(mock_popen.call_args[0][0])
            self.assertIn('download_by_name.py', call_args)
            self.assertNotIn('download_disease_drugs.py', call_args)
            self.assertIn('Schizophrenia', call_args)


class TestOpenFDALoader(unittest.TestCase):
    """Test openFDA loader."""
    
    @patch('openfda_loader.requests.get')
    def test_openfda_search(self, mock_get):
        """Test openFDA API search."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {
                    'openfda': {
                        'generic_name': ['Test Generic'],
                        'brand_name': ['Test Brand']
                    },
                    'indications_and_usage': ['For testing'],
                    'description': ['Test description'],
                    'products': [{'product_ndc': '12345-678'}]
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        from openfda_loader import search_drugs_by_condition
        
        drugs = search_drugs_by_condition("test condition", max_results=10)
        
        self.assertGreater(len(drugs), 0)
        self.assertEqual(drugs[0]['name'], 'Test Brand')
        self.assertEqual(drugs[0]['generic_name'], 'Test Generic')
        self.assertEqual(drugs[0]['source'], 'openfda')


class TestClinicalTrialsLoader(unittest.TestCase):
    """Test ClinicalTrials.gov loader."""
    
    @patch('clinicaltrials_loader.requests.get')
    def test_clinicaltrials_search(self, mock_get):
        """Test ClinicalTrials.gov API search."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'studies': [
                {
                    'protocolSection': {
                        'identificationModule': {
                            'nctId': 'NCT123456',
                            'briefTitle': 'Test Study'
                        },
                        'armsInterventionsModule': {
                            'interventions': [
                                {
                                    'name': 'Test Intervention',
                                    'type': 'DRUG'
                                }
                            ]
                        },
                        'conditionsModule': {
                            'conditions': [
                                {'name': 'Test Condition'}
                            ]
                        },
                        'descriptionModule': {
                            'briefSummary': 'Test summary'
                        }
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        from clinicaltrials_loader import search_drugs_by_condition
        
        drugs = search_drugs_by_condition("test condition", max_results=10)
        
        self.assertGreater(len(drugs), 0)
        self.assertEqual(drugs[0]['name'], 'Test Intervention')
        self.assertEqual(drugs[0]['intervention_type'], 'DRUG')
        self.assertEqual(drugs[0]['source'], 'clinicaltrials')


if __name__ == '__main__':
    unittest.main()

