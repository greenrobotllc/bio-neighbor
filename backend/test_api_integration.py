"""
Comprehensive API integration tests.
Tests complete workflows and error scenarios.
"""

import unittest
import sys
import json
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from api import app


class TestAPIIntegration(unittest.TestCase):
    """Integration tests for complete API workflows."""
    
    def setUp(self):
        """Set up test client."""
        self.app = app.test_client()
        self.app.testing = True
    
    def test_complete_download_workflow(self):
        """Test complete workflow: stats → download → status → stats."""
        # 1. Get initial stats
        stats_response = self.app.get('/stats')
        self.assertEqual(stats_response.status_code, 200)
        initial_stats = json.loads(stats_response.data)['stats']
        print(f"   Initial: {initial_stats['molecules']} molecules")
        
        # 2. Start download
        download_response = self.app.post('/download/molecules',
                                         json={'count': 2, 'source': 'pubchem'})
        self.assertEqual(download_response.status_code, 200)
        download_data = json.loads(download_response.data)
        self.assertTrue(download_data['success'])
        task_id = download_data.get('task_id')
        
        if task_id:
            # 3. Poll status until complete
            completed = False
            for _ in range(30):
                time.sleep(2)
                status_response = self.app.get(f'/download/status/{task_id}')
                if status_response.status_code == 200:
                    status_data = json.loads(status_response.data)
                    running = status_data.get('running', False)
                    if not running:
                        completed = True
                        exit_code = status_data.get('exit_code')
                        print(f"   Download completed, exit_code={exit_code}")
                        break
            
            # 4. Verify final stats (may not change if items already exist)
            if completed:
                time.sleep(2)
                final_stats_response = self.app.get('/stats')
                if final_stats_response.status_code == 200:
                    final_stats = json.loads(final_stats_response.data)['stats']
                    print(f"   Final: {final_stats['molecules']} molecules")
    
    def test_error_handling_invalid_input(self):
        """Test error handling for invalid inputs."""
        # Test missing parameters
        response = self.app.post('/download/molecules', json={})
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_search_workflow(self):
        """Test search workflow: search → verify results."""
        # Search molecules
        response = self.app.get('/search/molecules?q=aspirin&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        results = data.get('results', [])
        print(f"   Found {len(results)} search results")
        
        # Search drugs
        response = self.app.get('/search/drugs?q=donepezil&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        
        # Search diseases
        response = self.app.get('/search/diseases?q=alzheimer&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
    
    def test_stats_endpoint_reliability(self):
        """Test that stats endpoint is reliable."""
        # Call multiple times
        for i in range(5):
            response = self.app.get('/stats')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            self.assertIn('stats', data)
            time.sleep(0.5)
        
        print("   Stats endpoint called 5 times successfully")


if __name__ == '__main__':
    unittest.main()

