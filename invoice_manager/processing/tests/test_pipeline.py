"""
Unit tests for the OCR processing pipeline

This module tests the core pipeline functions, with a focus on parse_key_values
as specified in the checkpoint requirements.

Test Coverage:
- parse_key_values function (primary focus)
- Dependency checking
- Error handling
- Edge cases and malformed input
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from processing.pipeline import (
    parse_key_values,
    check_dependencies,
    _normalize_date,
    ParsingError,
    OCRError,
    PIPELINE_VERSION
)


class TestParseKeyValues(unittest.TestCase):
    """Test cases for the parse_key_values function"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.sample_invoice_text = """
        ABC CORPORATION LIMITED
        123 Business Street, New Delhi - 110001
        GSTIN: 07AAACB2343M1ZX
        
        INVOICE
        Invoice No: INV-2025-001
        Invoice Date: 13/09/2025
        Due Date: 27/09/2025
        
        Bill To:
        XYZ Company
        
        Description         Qty    Rate     Amount
        Software License     1    50000    50000
        Support Services     12    2500     30000
        
        Subtotal:                           80000
        GST (18%):                          14400
        Total Amount: ₹ 94,400
        
        Payment Terms: Net 15 days
        """
        
        self.minimal_invoice_text = """
        Invoice: 12345
        Amount: Rs. 1000
        """
        
        self.complex_invoice_text = """
        GREENTEK INDIA LIMITED
        Regd. Office: Plot No. 42, Sector 18, Gurgaon - 122001
        Corporate Office: Tower B, 5th Floor, DLF Cyber City, Gurgaon
        GSTIN: 06AABCG1234M1Z5
        CIN: U74899DL2010PTC999999
        
        TAX INVOICE
        
        Invoice Number: GT/2025/09/1234
        Invoice Date: 13-09-2025
        Place of Supply: Delhi
        
        Bill To:                           Ship To:
        Client Company Pvt Ltd             Same as billing address
        B-123, Sector 63
        Noida - 201301
        
        S.No  Description                    HSN     Qty    Rate      Amount
        1     CCTV Camera System            8525     5     12000     60000
        2     Installation Charges          9954     1     5000      5000
        3     AMC for 1 Year               9954     1     3000      3000
        
        Sub Total:                                                   68000.00
        CGST @ 9%:                                                   6120.00
        SGST @ 9%:                                                   6120.00
        IGST @ 0%:                                                   0.00
        
        Total Tax Amount:                                            12240.00
        Grand Total:                                                 ₹80,240.00
        
        Amount in Words: Eighty Thousand Two Hundred Forty Only
        
        Terms & Conditions:
        1. Payment due within 30 days
        2. Interest @ 24% p.a. will be charged on delayed payments
        """

    def test_parse_basic_invoice_fields(self):
        """Test extraction of basic invoice fields from well-formatted text"""
        result = parse_key_values(self.sample_invoice_text)
        
        # Check extracted values
        self.assertEqual(result['invoice_number'], 'INV-2025-001')
        self.assertEqual(result['invoice_date'], '2025-09-13')
        self.assertEqual(result['total_amount'], 94400.0)
        self.assertEqual(result['gstin'], '07AAACB2343M1ZX')
        self.assertEqual(result['currency'], 'INR')
        
        # Check confidence scores
        self.assertGreater(result['confidence_scores']['invoice_number'], 0.5)
        self.assertGreater(result['confidence_scores']['total_amount'], 0.5)
        self.assertGreater(result['confidence_scores']['gstin'], 0.8)

    def test_parse_complex_invoice(self):
        """Test parsing of complex invoice with multiple formats"""
        result = parse_key_values(self.complex_invoice_text)
        
        # Check extracted values
        self.assertEqual(result['invoice_number'], 'GT/2025/09/1234')
        self.assertEqual(result['invoice_date'], '2025-09-13')
        self.assertEqual(result['total_amount'], 80240.0)
        self.assertEqual(result['gstin'], '06AABCG1234M1Z5')
        self.assertEqual(result['currency'], 'INR')
        
        # Check supplier name extraction
        self.assertIsNotNone(result['supplier_name'])
        self.assertIn('LIMITED', result['supplier_name'])

    def test_parse_minimal_invoice(self):
        """Test parsing of minimal invoice with limited information"""
        result = parse_key_values(self.minimal_invoice_text)
        
        # Should extract basic fields
        self.assertEqual(result['invoice_number'], '12345')
        self.assertEqual(result['total_amount'], 1000.0)
        self.assertEqual(result['currency'], 'INR')
        
        # Fields not present should be None
        self.assertIsNone(result['gstin'])
        self.assertIsNone(result['invoice_date'])

    def test_parse_empty_text(self):
        """Test parsing of empty or whitespace-only text"""
        result = parse_key_values("")
        
        # All fields should be None
        for key in ['invoice_number', 'invoice_date', 'total_amount', 'gstin']:
            self.assertIsNone(result[key])
        
        # Confidence scores should be empty
        self.assertEqual(len(result['confidence_scores']), 0)

    def test_parse_malformed_text(self):
        """Test parsing of malformed or garbled text"""
        malformed_text = "asdlkjaslkdj 123 asldkjal $$$ ₹₹₹ random text"
        
        result = parse_key_values(malformed_text)
        
        # Should not crash and return structure
        self.assertIsInstance(result, dict)
        self.assertIn('invoice_number', result)
        self.assertIn('confidence_scores', result)

    def test_parse_multiple_amounts(self):
        """Test parsing when multiple amount patterns are present"""
        text_with_multiple_amounts = """
        Subtotal: Rs. 1000
        Tax: Rs. 180
        Total: Rs. 1180
        Grand Total: ₹ 1,180
        """
        
        result = parse_key_values(text_with_multiple_amounts)
        
        # Should extract the first/most relevant amount
        self.assertIsNotNone(result['total_amount'])
        self.assertGreater(result['total_amount'], 0)

    def test_parse_different_date_formats(self):
        """Test parsing of various date formats"""
        date_formats = [
            "Invoice Date: 13/09/2025",
            "Date: 13-09-2025", 
            "Dated: 13.09.2025",
            "Invoice Date: 13 Sep 2025",
            "Date: 13 September 2025"
        ]
        
        for date_text in date_formats:
            with self.subTest(date_format=date_text):
                result = parse_key_values(date_text)
                # Should extract some form of date
                self.assertIsNotNone(result['invoice_date'])

    def test_parse_different_currencies(self):
        """Test currency detection for different symbols"""
        test_cases = [
            ("Total: ₹ 1000", "INR"),
            ("Amount: Rs. 500", "INR"),
            ("Total: $100", "USD"),
            ("Amount: 50 USD", "USD")
        ]
        
        for text, expected_currency in test_cases:
            with self.subTest(text=text):
                result = parse_key_values(text)
                self.assertEqual(result['currency'], expected_currency)

    def test_parse_gstin_validation(self):
        """Test GSTIN pattern matching"""
        valid_gstin_text = "GSTIN: 07AAACB2343M1ZX"
        invalid_gstin_text = "GST: 123456789"
        
        # Valid GSTIN
        result = parse_key_values(valid_gstin_text)
        self.assertEqual(result['gstin'], '07AAACB2343M1ZX')
        
        # Invalid GSTIN should not be extracted
        result = parse_key_values(invalid_gstin_text)
        self.assertIsNone(result['gstin'])

    def test_confidence_scores_structure(self):
        """Test that confidence scores are properly structured"""
        result = parse_key_values(self.sample_invoice_text)
        
        # Confidence scores should be a dict
        self.assertIsInstance(result['confidence_scores'], dict)
        
        # All confidence scores should be between 0 and 1
        for field, score in result['confidence_scores'].items():
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_result_structure_completeness(self):
        """Test that the result contains all expected fields"""
        result = parse_key_values(self.sample_invoice_text)
        
        expected_fields = [
            'invoice_number', 'invoice_date', 'due_date', 'total_amount',
            'tax_amount', 'subtotal', 'currency', 'supplier_name',
            'supplier_address', 'gstin', 'confidence_scores'
        ]
        
        for field in expected_fields:
            self.assertIn(field, result)

    def test_parse_exception_handling(self):
        """Test that parsing handles exceptions gracefully"""
        # This should not raise an exception
        try:
            result = parse_key_values(None)  # Type error scenario
        except ParsingError:
            pass  # Expected behavior
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")


class TestDateNormalization(unittest.TestCase):
    """Test cases for the _normalize_date helper function"""
    
    def test_normalize_various_formats(self):
        """Test normalization of different date formats"""
        test_cases = [
            ("13/09/2025", "2025-09-13"),
            ("13-09-2025", "2025-09-13"),
            ("13.09.2025", "2025-09-13"),
            ("13/09/25", "2025-09-13"),
            ("2025-09-13", "2025-09-13"),
            ("13 Sep 2025", "2025-09-13")
        ]
        
        for input_date, expected_output in test_cases:
            with self.subTest(input_date=input_date):
                result = _normalize_date(input_date)
                self.assertEqual(result, expected_output)

    def test_normalize_invalid_dates(self):
        """Test handling of invalid date strings"""
        invalid_dates = ["invalid", "32/13/2025", "", "abc-def-ghi"]
        
        for invalid_date in invalid_dates:
            with self.subTest(invalid_date=invalid_date):
                result = _normalize_date(invalid_date)
                self.assertIsNone(result)


class TestDependencyChecking(unittest.TestCase):
    """Test cases for dependency checking functionality"""
    
    def test_check_dependencies_structure(self):
        """Test that dependency checking returns proper structure"""
        result = check_dependencies()
        
        # Should return a dictionary
        self.assertIsInstance(result, dict)
        
        # Should contain expected dependencies
        expected_deps = ['fitz', 'pdf2image', 'paddleocr', 'camelot', 'cv2', 'rapidfuzz']
        for dep in expected_deps:
            self.assertIn(dep, result)
            self.assertIsInstance(result[dep], bool)

    @patch('processing.pipeline.HAS_PADDLEOCR', False)
    def test_dependency_unavailable(self):
        """Test behavior when dependencies are unavailable"""
        result = check_dependencies()
        self.assertFalse(result['paddleocr'])


class TestErrorHandling(unittest.TestCase):
    """Test cases for error handling in the pipeline"""
    
    def test_parsing_error_inheritance(self):
        """Test that custom exceptions inherit properly"""
        self.assertTrue(issubclass(ParsingError, OCRError))
        self.assertTrue(issubclass(OCRError, Exception))

    def test_pipeline_version(self):
        """Test that pipeline version is defined"""
        self.assertIsInstance(PIPELINE_VERSION, str)
        self.assertRegex(PIPELINE_VERSION, r'\d+\.\d+\.\d+')


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)