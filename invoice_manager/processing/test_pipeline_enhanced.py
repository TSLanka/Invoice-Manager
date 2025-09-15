"""
Enhanced unit tests for OCR pipeline processing module.

Tests cover:
- Enhanced parsing with multiple invoice formats
- Robust supplier matching with various algorithms
- Date normalization and validation
- Amount and tax extraction improvements
- GSTIN and PAN validation
- Error handling and edge cases
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to the path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from invoice_manager.processing.pipeline import (
        detect_pdf_type, extract_text_searchable, parse_key_values, 
        match_supplier, ParsingError, OCRError, _normalize_date,
        _validate_gstin, _validate_pan, _clean_text_for_parsing,
        _normalize_company_name
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("Running with dummy implementations for testing...")
    
    # Dummy implementations for testing
    def detect_pdf_type(filepath): return "searchable"
    def extract_text_searchable(filepath): return "sample text"
    def parse_key_values(text): return {}
    def match_supplier(text, suppliers): return []
    def _normalize_date(date_str): return "2024-01-01"
    def _validate_gstin(gstin): return True
    def _validate_pan(pan): return True
    def _clean_text_for_parsing(text): return text.strip()
    def _normalize_company_name(name): return name.lower()
    
    class ParsingError(Exception): pass
    class OCRError(Exception): pass


class TestEnhancedParsing(unittest.TestCase):
    """Test enhanced parsing functionality."""
    
    def test_parse_key_values_indian_invoice(self):
        """Test parsing of Indian tax invoice format."""
        indian_invoice = """
        GREENTEK SOLUTIONS PRIVATE LIMITED
        123 Tech Park, Bangalore, Karnataka 560001
        GSTIN: 29AABCG1234A1Z5
        PAN: AABCG1234A
        
        TAX INVOICE
        Invoice No: INV-2024-001
        Invoice Date: 15/03/2024
        
        Description          Qty    Rate      Amount
        Software License     1      50000.00  50000.00
        
        Subtotal:                            50000.00
        CGST @ 9%:                            4500.00
        SGST @ 9%:                            4500.00
        Grand Total:                         59000.00
        """
        
        result = parse_key_values(indian_invoice)
        
        # Test extracted values
        self.assertEqual(result['invoice_number'], 'INV-2024-001')
        self.assertEqual(result['invoice_date'], '2024-03-15')
        self.assertEqual(result['total_amount'], 59000.0)
        self.assertEqual(result['tax_amount'], 9000.0)  # CGST + SGST
        self.assertEqual(result['gstin'], '29AABCG1234A1Z5')
        self.assertEqual(result['pan'], 'AABCG1234A')
        self.assertEqual(result['supplier_name'], 'GREENTEK SOLUTIONS PRIVATE LIMITED')
        self.assertEqual(result['currency'], 'INR')
        
        # Test confidence scores
        self.assertGreaterEqual(result['confidence_scores']['invoice_number'], 0.8)
        self.assertGreaterEqual(result['confidence_scores']['invoice_date'], 0.8)
        self.assertGreaterEqual(result['confidence_scores']['gstin'], 0.9)
    
    def test_parse_key_values_quotation_format(self):
        """Test parsing of quotation/estimate format."""
        quotation = """
        ACME INDUSTRIES LLP
        Plot 456, Industrial Area
        Delhi - 110020
        GST No: 07AABCA1234B1ZX
        
        QUOTATION NO: QUO-2024-0025
        Date: 22nd March 2024
        
        Item Details:
        Equipment Supply    Qty: 2    Rs. 25,000 each
        
        Total Amount: Rs. 50,000/-
        GST @ 18%: Rs. 9,000/-
        Net Payable: Rs. 59,000/-
        """
        
        result = parse_key_values(quotation)
        
        # Test extracted values
        self.assertEqual(result['invoice_number'], 'QUO-2024-0025')
        self.assertEqual(result['total_amount'], 50000.0)
        self.assertEqual(result['gstin'], '07AABCA1234B1ZX')
        self.assertEqual(result['supplier_name'], 'ACME INDUSTRIES LLP')
        self.assertEqual(result['currency'], 'INR')
    
    def test_parse_key_values_edge_cases(self):
        """Test parsing with edge cases and OCR errors."""
        ocr_text = """
        XYZ C0MPANY LTD  # OCR error: 0 instead of O
        Inv0ice Number: lNV-2024-OO2  # OCR errors: 0 for O, l for I
        Date: 15/O3/2024  # OCR error: O instead of 0
        Total: Rs. 1,25,000.00
        """
        
        result = parse_key_values(ocr_text)
        
        # Should handle OCR errors and still extract
        self.assertIsNotNone(result['invoice_number'])
        self.assertIsNotNone(result['total_amount'])
        
    def test_empty_and_invalid_input(self):
        """Test handling of empty and invalid inputs."""
        # Empty input
        result = parse_key_values("")
        self.assertIsNone(result['invoice_number'])
        
        # None input
        result = parse_key_values(None)
        self.assertIsNone(result['invoice_number'])
        
        # Gibberish input
        result = parse_key_values("asdfghjkl qwerty")
        self.assertIsNone(result['invoice_number'])


class TestEnhancedSupplierMatching(unittest.TestCase):
    """Test enhanced supplier matching functionality."""
    
    def setUp(self):
        """Set up test suppliers."""
        self.suppliers = [
            {'name': 'SUP001', 'supplier_name': 'Greentek Solutions Private Limited'},
            {'name': 'SUP002', 'supplier_name': 'ACME Industries LLP'},
            {'name': 'SUP003', 'supplier_name': 'ABC Corporation Ltd'},
            {'name': 'SUP004', 'supplier_name': 'Tech Solutions Pvt Ltd'},
            {'name': 'SUP005', 'supplier_name': 'Green Technologies'},
        ]
    
    @patch('invoice_manager.processing.pipeline.HAS_RAPIDFUZZ', True)
    def test_exact_match(self):
        """Test exact supplier name matching."""
        matches = match_supplier('Greentek Solutions Private Limited', self.suppliers, threshold=0.5)
        
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0]['supplier_name'], 'Greentek Solutions Private Limited')
        self.assertGreaterEqual(matches[0]['confidence'], 0.9)
    
    @patch('invoice_manager.processing.pipeline.HAS_RAPIDFUZZ', True)
    def test_partial_match(self):
        """Test partial supplier name matching."""
        matches = match_supplier('Greentek Solutions', self.suppliers, threshold=0.5)
        
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0]['supplier_name'], 'Greentek Solutions Private Limited')
        self.assertGreaterEqual(matches[0]['confidence'], 0.6)
    
    @patch('invoice_manager.processing.pipeline.HAS_RAPIDFUZZ', True)
    def test_abbreviation_match(self):
        """Test abbreviation matching."""
        matches = match_supplier('ACME IND', self.suppliers, threshold=0.5)
        
        self.assertGreater(len(matches), 0)
        # Should match ACME Industries LLP
        self.assertIn('ACME', matches[0]['supplier_name'])
    
    @patch('invoice_manager.processing.pipeline.HAS_RAPIDFUZZ', True)
    def test_case_insensitive_match(self):
        """Test case insensitive matching."""
        matches = match_supplier('greentek solutions pvt ltd', self.suppliers, threshold=0.5)
        
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0]['supplier_name'], 'Greentek Solutions Private Limited')
    
    @patch('invoice_manager.processing.pipeline.HAS_RAPIDFUZZ', False)
    def test_no_rapidfuzz(self):
        """Test behavior when rapidfuzz is not available."""
        with self.assertRaises(OCRError):
            match_supplier('Test Supplier', self.suppliers)
    
    def test_empty_supplier_list(self):
        """Test with empty supplier list."""
        matches = match_supplier('Test Supplier', [], threshold=0.5)
        self.assertEqual(len(matches), 0)
    
    def test_empty_supplier_text(self):
        """Test with empty supplier text."""
        matches = match_supplier('', self.suppliers, threshold=0.5)
        self.assertEqual(len(matches), 0)


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions for enhanced parsing."""
    
    def test_normalize_date(self):
        """Test date normalization function."""
        # Test various date formats
        test_cases = [
            ('15/03/2024', '2024-03-15'),
            ('15-03-2024', '2024-03-15'),
            ('15.03.2024', '2024-03-15'),
            ('15/03/24', '2024-03-15'),
            ('22nd March 2024', '2024-03-22'),
            ('Mar 15 2024', '2024-03-15'),
            ('15 Mar 2024', '2024-03-15'),
            ('2024/03/15', '2024-03-15'),
            ('invalid date', None),
            ('', None),
        ]
        
        for input_date, expected in test_cases:
            with self.subTest(input_date=input_date):
                result = _normalize_date(input_date)
                self.assertEqual(result, expected)
    
    def test_validate_gstin(self):
        """Test GSTIN validation."""
        valid_gstin = '29AABCG1234A1Z5'
        invalid_gstin = '29ABCG1234A1Z5'  # Wrong format
        
        self.assertTrue(_validate_gstin(valid_gstin))
        self.assertFalse(_validate_gstin(invalid_gstin))
        self.assertFalse(_validate_gstin(''))
        self.assertFalse(_validate_gstin('12345'))
    
    def test_validate_pan(self):
        """Test PAN validation."""
        valid_pan = 'AABCG1234A'
        invalid_pan = 'AABCG123A'  # Wrong length
        
        self.assertTrue(_validate_pan(valid_pan))
        self.assertFalse(_validate_pan(invalid_pan))
        self.assertFalse(_validate_pan(''))
        self.assertFalse(_validate_pan('12345'))
    
    def test_clean_text_for_parsing(self):
        """Test text cleaning function."""
        dirty_text = "Text with\tmultiple\n\n  spaces   and０１２fullwidth"
        cleaned = _clean_text_for_parsing(dirty_text)
        
        self.assertNotIn('\t', cleaned)
        self.assertNotIn('\n', cleaned)
        self.assertNotIn('０', cleaned)  # Should be replaced with 0
        self.assertNotIn('１', cleaned)  # Should be replaced with 1
        self.assertNotIn('２', cleaned)  # Should be replaced with 2
    
    def test_normalize_company_name(self):
        """Test company name normalization."""
        test_cases = [
            ('ABC Corporation Limited', 'abc corporation'),
            ('M/S XYZ Industries Pvt Ltd', 'xyz industries'),
            ('The Tech Solutions LLC', 'tech solutions'),
            ('ABC-Corp. Services', 'abc corp services'),
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = _normalize_company_name(input_name)
                self.assertEqual(result, expected)


class TestErrorHandling(unittest.TestCase):
    """Test error handling in parsing functions."""
    
    def test_parsing_error_handling(self):
        """Test that parsing errors are handled gracefully."""
        # Should not raise exception even with problematic input
        try:
            result = parse_key_values("Some random text with unicode: 🎉")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"parse_key_values raised unexpected exception: {e}")
    
    def test_confidence_scores_present(self):
        """Test that confidence scores are always included."""
        result = parse_key_values("Test invoice text")
        
        self.assertIn('confidence_scores', result)
        self.assertIsInstance(result['confidence_scores'], dict)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)