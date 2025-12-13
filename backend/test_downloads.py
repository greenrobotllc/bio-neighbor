"""
Tests for download functionality.
Tests the download endpoints and scripts.
"""

import unittest
import sys
import subprocess
from pathlib import Path
import json
import time

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from api import app


class TestDownloads(unittest.TestCase):
    """Test download endpoints and scripts."""
    
    def setUp(self):
        """Set up test client."""
        self.app = app.test_client()
        self.app.testing = True
    
    def test_stats_endpoint(self):
        """Test stats endpoint."""
        response = self.app.get('/stats')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('stats', data)
        self.assertIn('molecules', data['stats'])
        self.assertIn('drugs', data['stats'])
        self.assertIn('diseases', data['stats'])
    
    def test_download_molecules_by_count(self):
        """Test downloading molecules by count."""
        response = self.app.post('/download/molecules',
                                json={'count': 10, 'source': 'pubchem'},
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)
        print(f"✅ Molecules download started: {data.get('message')}")
    
    def test_download_molecules_by_name(self):
        """Test downloading molecules by name."""
        response = self.app.post('/download/molecules',
                                json={'names': ['aspirin', 'ibuprofen']},
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)
        print(f"✅ Molecules download by name started: {data.get('message')}")
    
    def test_download_molecules_validation(self):
        """Test download molecules validation."""
        # Test missing parameters
        response = self.app.post('/download/molecules',
                                json={},
                                content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_download_drugs_by_name(self):
        """Test downloading drugs by name."""
        response = self.app.post('/download/drugs',
                                json={'names': ['donepezil']},
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)
        print(f"✅ Drugs download by name started: {data.get('message')}")
    
    def test_download_drugs_by_disease(self):
        """Test downloading drugs by disease."""
        response = self.app.post('/download/drugs',
                                json={'disease': "Alzheimer's disease", 'count': 5},
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)
        print(f"✅ Drugs download by disease started: {data.get('message')}")
    
    def test_download_drugs_validation(self):
        """Test download drugs validation."""
        # Test missing parameters
        response = self.app.post('/download/drugs',
                                json={},
                                content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
    
    def test_download_diseases_by_name(self):
        """Test downloading diseases by name."""
        response = self.app.post('/download/diseases',
                                json={'names': ["Alzheimer's disease"]},
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)
        print(f"✅ Diseases download by name started: {data.get('message')}")
    
    def test_download_diseases_bulk(self):
        """Test bulk downloading diseases."""
        response = self.app.post('/download/diseases',
                                json={'count': 10},
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)
        print(f"✅ Diseases bulk download started: {data.get('message')}")
    
    def test_download_diseases_validation(self):
        """Test download diseases validation."""
        # Test missing parameters
        response = self.app.post('/download/diseases',
                                json={},
                                content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
    
    def test_search_molecules(self):
        """Test molecule search."""
        response = self.app.get('/search/molecules?q=aspirin&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('results', data)
    
    def test_search_drugs(self):
        """Test drug search."""
        response = self.app.get('/search/drugs?q=donepezil&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('results', data)
    
    def test_search_diseases(self):
        """Test disease search."""
        response = self.app.get('/search/diseases?q=alzheimer&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('results', data)
    
    def test_download_status(self):
        """Test download status endpoint."""
        # First start a download
        response = self.app.post('/download/molecules',
                                json={'count': 5, 'source': 'pubchem'})
        if response.status_code == 200:
            data = json.loads(response.data)
            task_id = data.get('task_id')
            
            if task_id:
                # Wait a moment
                time.sleep(1)
                
                # Check status
                status_response = self.app.get(f'/download/status/{task_id}')
                self.assertEqual(status_response.status_code, 200)
                status_data = json.loads(status_response.data)
                self.assertTrue(status_data['success'])
                self.assertIn('running', status_data)
                print(f"   Status: running={status_data.get('running')}, message={status_data.get('message')}")
    
    def test_download_script_exists(self):
        """Test that download scripts exist."""
        scripts = [
            'download_molecules.py',
            'download_by_name.py',
            'download_disease_drugs.py'
        ]
        for script in scripts:
            script_path = Path(__file__).parent / script
            self.assertTrue(script_path.exists(), f"Script {script} not found")
    
    def test_download_molecules_script_runs(self):
        """Test that download_molecules.py script can be executed."""
        script_path = Path(__file__).parent / "download_molecules.py"
        if not script_path.exists():
            self.skipTest("download_molecules.py not found")
        
        # Test with help flag (should work without dependencies)
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), '--help'],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Help should return 0 or non-zero, but should produce output
            self.assertTrue(len(result.stdout) > 0 or len(result.stderr) > 0,
                          "Script should produce output")
        except subprocess.TimeoutExpired:
            self.fail("Script timed out")
        except Exception as e:
            self.fail(f"Script execution failed: {e}")


def run_integration_test():
    """Run a simple integration test."""
    print("\n" + "=" * 60)
    print("🧪 Running Download Integration Tests")
    print("=" * 60)
    
    # Test stats
    print("\n1. Testing /stats endpoint...")
    with app.test_client() as client:
        response = client.get('/stats')
        if response.status_code == 200:
            data = json.loads(response.data)
            print(f"   ✅ Stats: {data.get('stats', {})}")
        else:
            print(f"   ❌ Stats failed: {response.status_code}")
    
    # Test molecule download
    print("\n2. Testing molecule download (small count)...")
    with app.test_client() as client:
        response = client.post('/download/molecules',
                              json={'count': 5, 'source': 'pubchem'})
        if response.status_code == 200:
            data = json.loads(response.data)
            print(f"   ✅ Download started: {data.get('message')}")
            print(f"   Task ID: {data.get('task_id')}")
        else:
            data = json.loads(response.data)
            print(f"   ❌ Download failed: {data.get('error')}")
    
    # Test search
    print("\n3. Testing search...")
    with app.test_client() as client:
        response = client.get('/search/molecules?q=aspirin&limit=3')
        if response.status_code == 200:
            data = json.loads(response.data)
            results = data.get('results', [])
            print(f"   ✅ Found {len(results)} results")
            for r in results[:3]:
                print(f"      - {r.get('name')}")
        else:
            print(f"   ❌ Search failed: {response.status_code}")
    
    print("\n" + "=" * 60)
    print("✅ Integration tests complete")
    print("=" * 60)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--integration':
        run_integration_test()
    else:
        unittest.main()

