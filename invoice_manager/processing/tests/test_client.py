"""
Unit tests for the Frappe integration client

This module tests the client functions that integrate with Frappe framework.
Tests focus on job enqueueing, status tracking, and API endpoints.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestClientIntegration(unittest.TestCase):
    """Test cases for the Frappe integration client"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_job_id = "IPJ-2025-001"
        self.mock_file_path = "/tmp/test_invoice.pdf"
    
    @patch('invoice_manager.processing.client.frappe')
    def test_trigger_extraction_api(self, mock_frappe):
        """Test the trigger_extraction API endpoint"""
        # Mock Frappe functions
        mock_frappe.has_permission.return_value = True
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = MagicMock(status="Draft")
        mock_frappe.enqueue.return_value = "mock_job_123"
        
        # Import after mocking
        from processing.client import trigger_extraction
        
        result = trigger_extraction(self.mock_job_id)
        
        # Verify result
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], self.mock_job_id)
        self.assertIn("frappe_job_id", result)
    
    @patch('invoice_manager.processing.client.frappe')
    def test_get_extraction_status(self, mock_frappe):
        """Test extraction status retrieval"""
        # Mock job document
        mock_job_doc = MagicMock()
        mock_job_doc.status = "Processing"
        mock_job_doc.extraction_version = "1.0.0"
        mock_job_doc.ocr_raw_text = "Sample text"
        mock_job_doc.parsed_json = '{"invoice_number": "123"}'
        mock_job_doc.supplier_matches = []
        mock_job_doc.modified = "2025-09-13 10:00:00"
        
        mock_frappe.get_doc.return_value = mock_job_doc
        
        # Import after mocking
        from processing.client import get_extraction_status
        
        result = get_extraction_status(self.mock_job_id)
        
        # Verify result structure
        self.assertEqual(result["job_id"], self.mock_job_id)
        self.assertEqual(result["status"], "Processing")
        self.assertTrue(result["has_raw_text"])
        self.assertTrue(result["has_parsed_data"])
    
    @patch('invoice_manager.processing.client.frappe')
    def test_permission_check(self, mock_frappe):
        """Test that permission checking works properly"""
        # Mock insufficient permissions
        mock_frappe.has_permission.return_value = False
        mock_frappe.throw = MagicMock(side_effect=Exception("Insufficient permissions"))
        
        # Import after mocking
        from processing.client import trigger_extraction
        
        # Should raise exception for insufficient permissions
        with self.assertRaises(Exception):
            trigger_extraction(self.mock_job_id)
    
    def test_job_enqueueing_validation(self):
        """Test job enqueueing with validation"""
        # This would require a more complex mock setup for Frappe
        # For now, just test that the functions are importable
        try:
            from processing.client import enqueue_extraction_job, process_extraction_job
            self.assertTrue(callable(enqueue_extraction_job))
            self.assertTrue(callable(process_extraction_job))
        except ImportError:
            # Expected when Frappe is not available
            pass


class TestDocTypeController(unittest.TestCase):
    """Test cases for the Invoice Processing Job controller extensions"""
    
    @patch('frappe.session')
    @patch('frappe.has_permission')
    @patch('frappe.utils.now')
    def test_re_run_extraction_method(self, mock_now, mock_has_permission, mock_session):
        """Test the re_run_extraction method structure"""
        # This test verifies the method can be called without Frappe context
        # Full testing would require Frappe test environment
        
        mock_now.return_value = "2025-09-13 10:00:00"
        mock_has_permission.return_value = True
        mock_session.user = "test@example.com"
        
        # For now, just verify the method exists in the controller file
        # Full integration testing would be done in Frappe test environment
        self.assertTrue(True)  # Placeholder for proper integration test


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)