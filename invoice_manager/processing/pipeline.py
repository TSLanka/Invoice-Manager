"""
Core OCR Processing Pipeline

This module provides framework-agnostic OCR processing functions for invoice data extraction.
All functions are designed to work independently of Frappe/ERPNext framework for maximum
reusability and testability.

Dependencies:
- PaddleOCR for text recognition
- pdf2image for PDF to image conversion  
- PyMuPDF (fitz) for PDF text extraction
- Camelot for table extraction
- OpenCV for image processing
- rapidfuzz for fuzzy string matching

Author: Invoice Manager Development Team
Version: 1.0.0
"""

import io
import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Union, Any
from pathlib import Path
import tempfile
import os

# Third-party imports (will be optional dependencies)
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from pdf2image import convert_from_path, convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    from paddleocr import PaddleOCR
    HAS_PADDLEOCR = True
except ImportError:
    HAS_PADDLEOCR = False

try:
    import camelot
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    # Create dummy numpy for type hints when not available
    class DummyNumpy:
        ndarray = object
    np = DummyNumpy()

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# Configure logging
logger = logging.getLogger(__name__)

# Pipeline version for tracking
PIPELINE_VERSION = "1.0.0"


class OCRError(Exception):
    """Base exception for OCR processing errors"""
    pass


class PDFError(OCRError):
    """Exception for PDF processing errors"""
    pass


class ImageProcessingError(OCRError):
    """Exception for image processing errors"""
    pass


class ParsingError(OCRError):
    """Exception for data parsing errors"""
    pass


def check_dependencies() -> Dict[str, bool]:
    """
    Check availability of optional OCR dependencies.
    
    Returns:
        Dict[str, bool]: Dictionary of dependency names and availability status
    """
    return {
        'fitz': HAS_FITZ,
        'pdf2image': HAS_PDF2IMAGE,
        'paddleocr': HAS_PADDLEOCR,
        'camelot': HAS_CAMELOT,
        'cv2': HAS_CV2,
        'rapidfuzz': HAS_RAPIDFUZZ
    }


def detect_pdf_type(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Analyze PDF structure to determine processing strategy.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Dict containing:
        - is_searchable: bool
        - page_count: int
        - has_images: bool
        - text_coverage: float (0-1)
        - file_size_mb: float
        
    Raises:
        PDFError: If PDF cannot be processed
    """
    if not HAS_FITZ:
        raise PDFError("PyMuPDF (fitz) not available. Install with: pip install PyMuPDF")
    
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            raise PDFError(f"File not found: {file_path}")
        
        doc = fitz.open(str(file_path))
        page_count = len(doc)
        total_chars = 0
        has_images = False
        
        # Analyze first few pages for performance
        sample_pages = min(3, page_count)
        
        for page_num in range(sample_pages):
            page = doc[page_num]
            
            # Check for text content
            text = page.get_text()
            total_chars += len(text.strip())
            
            # Check for images
            if page.get_images():
                has_images = True
        
        doc.close()
        
        # Calculate text coverage (rough estimate)
        text_coverage = min(1.0, total_chars / (sample_pages * 500))  # Assume 500 chars per page is good coverage
        is_searchable = text_coverage > 0.1  # >10% text coverage considered searchable
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        
        return {
            'is_searchable': is_searchable,
            'page_count': page_count,
            'has_images': has_images,
            'text_coverage': text_coverage,
            'file_size_mb': file_size_mb
        }
        
    except Exception as e:
        raise PDFError(f"Failed to analyze PDF: {str(e)}")


def extract_text_searchable(file_path: Union[str, Path]) -> str:
    """
    Extract text directly from searchable PDF.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        str: Extracted text content
        
    Raises:
        PDFError: If text extraction fails
    """
    if not HAS_FITZ:
        raise PDFError("PyMuPDF (fitz) not available. Install with: pip install PyMuPDF")
    
    try:
        doc = fitz.open(str(file_path))
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            full_text += f"\n--- Page {page_num + 1} ---\n{text}"
        
        doc.close()
        
        return full_text.strip()
        
    except Exception as e:
        raise PDFError(f"Failed to extract text from PDF: {str(e)}")


def extract_images_from_pdf(file_path: Union[str, Path], dpi: int = 300) -> List[np.ndarray]:
    """
    Convert PDF pages to images for OCR processing.
    
    Args:
        file_path: Path to the PDF file
        dpi: Resolution for image conversion (default: 300)
        
    Returns:
        List[np.ndarray]: List of page images as numpy arrays
        
    Raises:
        ImageProcessingError: If image extraction fails
    """
    if not HAS_PDF2IMAGE:
        raise ImageProcessingError("pdf2image not available. Install with: pip install pdf2image")
    
    if not HAS_CV2:
        raise ImageProcessingError("OpenCV not available. Install with: pip install opencv-python")
    
    try:
        # Convert PDF to images
        images = convert_from_path(str(file_path), dpi=dpi)
        
        # Convert PIL images to numpy arrays
        cv_images = []
        for img in images:
            # Convert PIL image to RGB numpy array
            img_array = np.array(img)
            # Convert RGB to BGR for OpenCV
            if len(img_array.shape) == 3:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            cv_images.append(img_array)
        
        return cv_images
        
    except Exception as e:
        raise ImageProcessingError(f"Failed to extract images from PDF: {str(e)}")


def ocr_images_paddle(images: List[np.ndarray], lang: str = 'en') -> List[Dict[str, Any]]:
    """
    Perform OCR on images using PaddleOCR.
    
    Args:
        images: List of images as numpy arrays
        lang: Language code for OCR (default: 'en')
        
    Returns:
        List[Dict]: OCR results for each image with text and confidence scores
        
    Raises:
        OCRError: If OCR processing fails
    """
    if not HAS_PADDLEOCR:
        raise OCRError("PaddleOCR not available. Install with: pip install paddleocr")
    
    try:
        # Initialize PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        
        results = []
        
        for idx, image in enumerate(images):
            logger.info(f"Processing image {idx + 1}/{len(images)} with PaddleOCR")
            
            # Perform OCR
            ocr_result = ocr.ocr(image, cls=True)
            
            # Extract text and confidence scores
            page_text = ""
            confidence_scores = []
            
            if ocr_result and ocr_result[0]:
                for line in ocr_result[0]:
                    if line:
                        bbox, (text, confidence) = line
                        page_text += text + " "
                        confidence_scores.append(confidence)
            
            # Calculate average confidence
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            results.append({
                'page_number': idx + 1,
                'text': page_text.strip(),
                'confidence': avg_confidence,
                'word_count': len(page_text.split()),
                'raw_result': ocr_result
            })
        
        return results
        
    except Exception as e:
        raise OCRError(f"PaddleOCR processing failed: {str(e)}")


def extract_tables_with_camelot(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Extract tables from PDF using Camelot.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        List[Dict]: Extracted tables with metadata
        
    Raises:
        OCRError: If table extraction fails
    """
    if not HAS_CAMELOT:
        raise OCRError("Camelot not available. Install with: pip install camelot-py[cv]")
    
    try:
        # Extract tables using lattice method (for bordered tables)
        tables_lattice = camelot.read_pdf(str(file_path), flavor='lattice')
        
        # Extract tables using stream method (for non-bordered tables)
        tables_stream = camelot.read_pdf(str(file_path), flavor='stream')
        
        all_tables = []
        
        # Process lattice tables
        for idx, table in enumerate(tables_lattice):
            all_tables.append({
                'table_id': f"lattice_{idx}",
                'page': table.page,
                'method': 'lattice',
                'accuracy': table.accuracy,
                'data': table.df.to_dict('records'),
                'shape': table.shape
            })
        
        # Process stream tables
        for idx, table in enumerate(tables_stream):
            all_tables.append({
                'table_id': f"stream_{idx}",
                'page': table.page,
                'method': 'stream',
                'accuracy': table.accuracy,
                'data': table.df.to_dict('records'),
                'shape': table.shape
            })
        
        # Sort by page and accuracy
        all_tables.sort(key=lambda x: (x['page'], -x['accuracy']))
        
        return all_tables
        
    except Exception as e:
        raise OCRError(f"Camelot table extraction failed: {str(e)}")


def parse_key_values(text: str) -> Dict[str, Any]:
    """
    Extract key invoice fields using regex patterns and heuristics.
    
    Args:
        text: Raw text content from invoice
        
    Returns:
        Dict containing extracted fields:
        - invoice_number: str
        - invoice_date: str (ISO format)
        - due_date: str (ISO format)
        - total_amount: float
        - tax_amount: float
        - subtotal: float
        - currency: str
        - supplier_name: str
        - supplier_address: str
        - gstin: str
        - confidence_scores: Dict[str, float]
        
    Raises:
        ParsingError: If parsing fails completely
    """
    try:
        result = {
            'invoice_number': None,
            'invoice_date': None,
            'due_date': None,
            'total_amount': None,
            'tax_amount': None,
            'subtotal': None,
            'currency': None,
            'supplier_name': None,
            'supplier_address': None,
            'gstin': None,
            'confidence_scores': {}
        }
        
        # Clean text for processing
        text = text.replace('\n', ' ').replace('\t', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Invoice Number patterns
        invoice_patterns = [
            r'invoice\s*(?:no|number|#)[\s:]+([A-Z0-9\-/]+)',
            r'bill\s*(?:no|number|#)[\s:]+([A-Z0-9\-/]+)',
            r'inv[\s\#]+([A-Z0-9\-/]+)',
            r'invoice[\s:]+([A-Z0-9\-/]+)'
        ]
        
        for pattern in invoice_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['invoice_number'] = match.group(1).strip()
                result['confidence_scores']['invoice_number'] = 0.8
                break
        
        # Date patterns (supports various formats)
        date_patterns = [
            r'(?:invoice\s*date|date|dated)[\s:]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
            r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
            r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2,4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                # Basic date normalization (would need more robust date parsing)
                result['invoice_date'] = _normalize_date(date_str)
                result['confidence_scores']['invoice_date'] = 0.7
                break
        
        # Amount patterns
        amount_patterns = [
            r'total[\s:]+(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)',
            r'grand\s*total[\s:]+(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)',
            r'amount[\s:]+(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)',
            r'(?:rs\.?|₹)\s*([0-9,]+\.?\d*)'
        ]
        
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    result['total_amount'] = float(amount_str)
                    result['confidence_scores']['total_amount'] = 0.7
                    break
                except ValueError:
                    continue
        
        # Tax amount patterns
        tax_patterns = [
            r'(?:gst|tax|vat)[\s:]+(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)',
            r'(?:cgst|sgst|igst)[\s:]+(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)'
        ]
        
        for pattern in tax_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tax_str = match.group(1).replace(',', '')
                try:
                    result['tax_amount'] = float(tax_str)
                    result['confidence_scores']['tax_amount'] = 0.6
                    break
                except ValueError:
                    continue
        
        # GSTIN pattern
        gstin_pattern = r'(?:gstin|gst\s*no)[\s:]+([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})'
        match = re.search(gstin_pattern, text, re.IGNORECASE)
        if match:
            result['gstin'] = match.group(1).upper()
            result['confidence_scores']['gstin'] = 0.9
        
        # Currency detection
        if '₹' in text or 'rs.' in text.lower() or 'inr' in text.lower():
            result['currency'] = 'INR'
            result['confidence_scores']['currency'] = 0.8
        elif '$' in text or 'usd' in text.lower():
            result['currency'] = 'USD'
            result['confidence_scores']['currency'] = 0.8
        
        # Supplier name (first line/entity that looks like a company)
        lines = text.split('.')[:5]  # Check first few segments
        for line in lines:
            line = line.strip()
            if len(line) > 10 and any(word in line.lower() for word in ['ltd', 'limited', 'pvt', 'inc', 'corp']):
                result['supplier_name'] = line
                result['confidence_scores']['supplier_name'] = 0.6
                break
        
        return result
        
    except Exception as e:
        raise ParsingError(f"Key-value parsing failed: {str(e)}")


def match_supplier(supplier_text: str, supplier_list: List[Dict[str, str]], threshold: float = 0.8) -> List[Dict[str, Any]]:
    """
    Match extracted supplier name against known suppliers using fuzzy matching.
    
    Args:
        supplier_text: Extracted supplier name/text
        supplier_list: List of known suppliers with 'name' and 'supplier_name' fields
        threshold: Minimum similarity score (0-1)
        
    Returns:
        List[Dict]: Matched suppliers with confidence scores, sorted by relevance
        
    Raises:
        OCRError: If fuzzy matching fails
    """
    if not HAS_RAPIDFUZZ:
        raise OCRError("rapidfuzz not available. Install with: pip install rapidfuzz")
    
    if not supplier_text or not supplier_list:
        return []
    
    try:
        matches = []
        
        for supplier in supplier_list:
            supplier_name = supplier.get('supplier_name') or supplier.get('name', '')
            if not supplier_name:
                continue
            
            # Calculate similarity scores using different algorithms
            ratio_score = fuzz.ratio(supplier_text.lower(), supplier_name.lower()) / 100
            partial_score = fuzz.partial_ratio(supplier_text.lower(), supplier_name.lower()) / 100
            token_score = fuzz.token_sort_ratio(supplier_text.lower(), supplier_name.lower()) / 100
            
            # Weighted average (partial ratio gets higher weight for substring matches)
            combined_score = (ratio_score * 0.3 + partial_score * 0.5 + token_score * 0.2)
            
            if combined_score >= threshold:
                matches.append({
                    'supplier_name': supplier_name,
                    'supplier_code': supplier.get('name', ''),
                    'confidence': combined_score,
                    'similarity_scores': {
                        'ratio': ratio_score,
                        'partial': partial_score,
                        'token_sort': token_score
                    }
                })
        
        # Sort by confidence score (highest first)
        matches.sort(key=lambda x: x['confidence'], reverse=True)
        
        return matches[:10]  # Return top 10 matches
        
    except Exception as e:
        raise OCRError(f"Supplier matching failed: {str(e)}")


def _normalize_date(date_str: str) -> Optional[str]:
    """
    Normalize various date formats to ISO format (YYYY-MM-DD).
    
    Args:
        date_str: Raw date string
        
    Returns:
        str: ISO formatted date or None if parsing fails
    """
    try:
        from datetime import datetime
        
        # Common date formats
        formats = [
            '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
            '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
            '%m/%d/%Y', '%m-%d-%Y', '%m.%d.%Y',
            '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d',
            '%d %b %Y', '%d %B %Y'
        ]
        
        date_str = date_str.strip()
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return None
        
    except Exception:
        return None


# TODO: Add more sophisticated table parsing for line items
# TODO: Implement confidence scoring improvements
# TODO: Add support for multi-language OCR
# TODO: Optimize image preprocessing for better OCR accuracy