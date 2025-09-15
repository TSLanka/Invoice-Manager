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


def detect_pdf_type(file_path: Union[str, Path]) -> str:
    """
    Detect PDF type for processing strategy selection.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        str: PDF type - 'searchable', 'image', 'mixed', or 'empty'
        
    Raises:
        PDFError: If PDF cannot be processed
    """
    if not HAS_FITZ:
        raise PDFError("PyMuPDF (fitz) not available. Install with: pip install PyMuPDF")
    
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return "empty"
        
        doc = fitz.open(str(file_path))
        page_count = len(doc)
        
        if page_count == 0:
            doc.close()
            return "empty"
        
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
        
        # Determine PDF type based on content
        if text_coverage > 0.7:
            return "searchable"
        elif text_coverage > 0.1 and has_images:
            return "mixed"
        elif has_images or text_coverage <= 0.1:
            return "image"
        else:
            return "empty"
        
    except Exception as e:
        logger.warning(f"Failed to analyze PDF {file_path}: {str(e)}")
        return "empty"


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
    Convert PDF pages to images for OCR processing with enhanced preprocessing.
    
    Args:
        file_path: Path to the PDF file
        dpi: Resolution for image conversion (default: 300)
        
    Returns:
        List[np.ndarray]: List of preprocessed page images as numpy arrays
        
    Raises:
        ImageProcessingError: If image extraction fails
    """
    if not HAS_PDF2IMAGE:
        raise ImageProcessingError("pdf2image not available. Install with: pip install pdf2image")
    
    if not HAS_CV2:
        raise ImageProcessingError("OpenCV not available. Install with: pip install opencv-python")
    
    try:
        logger.info(f"Converting PDF to images at {dpi} DPI")
        
        # Convert PDF to images with high quality
        images = convert_from_path(
            str(file_path), 
            dpi=dpi,
            output_folder=None,
            first_page=None,
            last_page=None,
            fmt='png',
            thread_count=1,
            userpw=None,
            use_cropbox=False,
            strict=False
        )
        
        # Convert PIL images to numpy arrays and preprocess
        cv_images = []
        for idx, img in enumerate(images):
            logger.info(f"Preprocessing image {idx + 1}/{len(images)}")
            
            # Convert PIL image to RGB numpy array
            img_array = np.array(img)
            
            # Convert RGB to BGR for OpenCV
            if len(img_array.shape) == 3:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Apply image preprocessing for better OCR
            processed_img = _preprocess_image_for_ocr(img_array)
            cv_images.append(processed_img)
        
        logger.info(f"Successfully converted PDF to {len(cv_images)} preprocessed images")
        return cv_images
        
    except Exception as e:
        raise ImageProcessingError(f"Failed to extract images from PDF: {str(e)}")


def _preprocess_image_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Preprocess image for optimal OCR accuracy.
    
    Args:
        image: Input image as numpy array
        
    Returns:
        np.ndarray: Preprocessed image
    """
    try:
        # Convert to grayscale if colored
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # Apply noise reduction
        denoised = cv2.medianBlur(gray, 3)
        
        # Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # Apply Gaussian blur to smooth the image slightly
        blurred = cv2.GaussianBlur(enhanced, (1, 1), 0)
        
        # Apply threshold to get binary image (black text on white background)
        # Use adaptive threshold for better results with varying lighting
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Morphological operations to clean up the image
        kernel = np.ones((1, 1), np.uint8)
        
        # Opening (erosion followed by dilation) to remove noise
        opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # Closing (dilation followed by erosion) to fill gaps
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel)
        
        return closed
        
    except Exception as e:
        logger.warning(f"Image preprocessing failed, using original: {str(e)}")
        return image


def ocr_images_paddle(images: List[np.ndarray], lang: str = 'en') -> List[Dict[str, Any]]:
    """
    Perform enhanced OCR on images using PaddleOCR with optimized settings.
    
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
        logger.info(f"Initializing PaddleOCR with language: {lang}")
        
        # Initialize PaddleOCR with minimal settings for maximum compatibility
        ocr = PaddleOCR(use_angle_cls=True, lang=lang)
        
        results = []
        
        for idx, image in enumerate(images):
            logger.info(f"Processing image {idx + 1}/{len(images)} with PaddleOCR")
            
            # Perform OCR on the image
            ocr_result = ocr.ocr(image, cls=True)
            
            # Extract text and confidence scores
            page_text = ""
            confidence_scores = []
            word_details = []
            
            if ocr_result and ocr_result[0]:
                for line in ocr_result[0]:
                    if line and len(line) >= 2:
                        bbox, text_info = line
                        
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text, confidence = text_info
                            
                            # Filter out low-confidence text
                            if confidence >= 0.5 and text.strip():
                                page_text += text + " "
                                confidence_scores.append(confidence)
                                
                                word_details.append({
                                    'text': text,
                                    'confidence': confidence,
                                    'bbox': bbox
                                })
            
            # Calculate average confidence
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            # Additional text processing
            processed_text = _post_process_ocr_text(page_text.strip())
            
            results.append({
                'page_number': idx + 1,
                'text': processed_text,
                'raw_text': page_text.strip(),
                'confidence': avg_confidence,
                'word_count': len(processed_text.split()),
                'word_details': word_details,
                'raw_result': ocr_result
            })
            
            logger.info(f"Page {idx + 1}: Extracted {len(processed_text.split())} words with {avg_confidence:.2f} confidence")
        
        return results
        
    except Exception as e:
        raise OCRError(f"PaddleOCR processing failed: {str(e)}")


def _post_process_ocr_text(text: str) -> str:
    """
    Post-process OCR text to fix common errors and improve readability.
    
    Args:
        text: Raw OCR text
        
    Returns:
        str: Processed text
    """
    if not text:
        return ""
    
    try:
        # Fix common OCR errors
        processed = text
        
        # Replace common character substitutions
        char_replacements = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            'О': '0', 'о': '0', 'І': '1', 'і': '1', 'Ι': 'I',
            'Ο': 'O', 'ο': 'o', '|': 'I', '!': 'I', '@': 'a',
            '$': 'S', '€': 'E', '£': 'L', '¢': 'c'
        }
        
        for old_char, new_char in char_replacements.items():
            processed = processed.replace(old_char, new_char)
        
        # Fix spacing issues
        processed = re.sub(r'\s+', ' ', processed)  # Multiple spaces to single space
        processed = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', processed)  # Add space between letter and digit
        processed = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', processed)  # Add space between digit and letter
        
        # Fix punctuation spacing
        processed = re.sub(r'([.,:;!?])([a-zA-Z])', r'\1 \2', processed)
        
        # Remove extra whitespace
        processed = processed.strip()
        
        return processed
        
    except Exception as e:
        logger.warning(f"OCR text post-processing failed: {str(e)}")
        return text


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
    Extract key invoice fields using enhanced regex patterns and heuristics.
    
    Enhanced features:
    - Multiple pattern variations for Indian invoice formats
    - Improved confidence scoring based on pattern specificity
    - Better handling of OCR errors and variations
    - Support for various currency formats
    - Enhanced supplier name extraction
    
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
        - pan: str
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
            'pan': None,
            'confidence_scores': {}
        }
        
        if not text or not text.strip():
            return result
        
        # Clean and normalize text for processing
        cleaned_text = _clean_text_for_parsing(text)
        original_text = text  # Keep original for address extraction
        
        # Enhanced Invoice Number patterns with confidence scoring
        invoice_patterns = [
            # High confidence patterns (0.9)
            (r'tax\s*invoice\s*(?:no|number|#)[\s:\.]+([A-Z0-9\-/\\]+)', 0.9),
            (r'invoice\s*(?:no|number|#)[\s:\.]+([A-Z0-9\-/\\]{3,})', 0.9),
            (r'bill\s*(?:no|number|#)[\s:\.]+([A-Z0-9\-/\\]{3,})', 0.85),
            # Medium confidence patterns (0.7-0.8)
            (r'inv[\s\#:\.]+([A-Z0-9\-/\\]{3,})', 0.8),
            (r'invoice[\s:\.]+([A-Z0-9\-/\\]{3,})', 0.75),
            (r'doc[\s\#:\.]*(?:no|number)?[\s:\.]*([A-Z0-9\-/\\]{4,})', 0.7),
            # Lower confidence patterns (0.6)
            (r'ref[\s\#:\.]*(?:no)?[\s:\.]*([A-Z0-9\-/\\]{3,})', 0.6),
            (r'quotation[\s\#:\.]*(?:no)?[\s:\.]*([A-Z0-9\-/\\]{3,})', 0.6)
        ]
        
        for pattern, confidence in invoice_patterns:
            match = re.search(pattern, cleaned_text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                # Validate invoice number format
                if _is_valid_invoice_number(candidate):
                    result['invoice_number'] = candidate
                    result['confidence_scores']['invoice_number'] = confidence
                    break
        
        # Enhanced Date patterns with better validation
        date_patterns = [
            # High confidence date patterns (0.8-0.9)
            (r'(?:invoice\s*date|dated|date\s*of\s*invoice)[\s:\.]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 0.9),
            (r'(?:bill\s*date|billing\s*date)[\s:\.]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 0.85),
            # Medium confidence patterns (0.7)
            (r'date[\s:\.]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 0.7),
            (r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})', 0.75),  # Full year format
            (r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2,4})', 0.8),
            (r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2})', 0.65),  # Two digit year
        ]
        
        for pattern, confidence in date_patterns:
            match = re.search(pattern, cleaned_text, re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                normalized_date = _normalize_date(date_str)
                if normalized_date:
                    result['invoice_date'] = normalized_date
                    result['confidence_scores']['invoice_date'] = confidence
                    break
        
        # Enhanced Amount patterns with better currency handling
        amount_patterns = [
            # High confidence total amount patterns (0.85-0.9)
            (r'(?:grand\s*total|net\s*total|total\s*amount)[\s:\.]*(?:rs\.?|₹|inr)?\s*([0-9,]+\.?\d*)', 0.9),
            (r'(?:amount\s*payable|total\s*payable)[\s:\.]*(?:rs\.?|₹|inr)?\s*([0-9,]+\.?\d*)', 0.85),
            # Medium confidence patterns (0.7-0.8)
            (r'total[\s:\.]*(?:rs\.?|₹|inr)?\s*([0-9,]+\.?\d*)', 0.8),
            (r'amount[\s:\.]*(?:rs\.?|₹|inr)?\s*([0-9,]+\.?\d*)', 0.75),
            (r'(?:rs\.?|₹)\s*([0-9,]+\.?\d*)', 0.7),
            # Lower confidence patterns (0.6)
            (r'balance[\s:\.]*(?:rs\.?|₹|inr)?\s*([0-9,]+\.?\d*)', 0.6)
        ]
        
        for pattern, confidence in amount_patterns:
            match = re.search(pattern, cleaned_text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '').replace(' ', '')
                try:
                    amount = float(amount_str)
                    # Validate amount (reasonable range for invoices)
                    if 0.01 <= amount <= 99999999:
                        result['total_amount'] = amount
                        result['confidence_scores']['total_amount'] = confidence
                        break
                except ValueError:
                    continue
        
        # Enhanced Tax amount patterns
        tax_patterns = [
            # Specific GST components (0.85-0.9)
            (r'(?:total\s*)?gst[\s:\.]*(?:amount)?[\s:\.]*(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)', 0.9),
            (r'cgst[\s:\.]*(?:@\s*\d+(?:\.\d+)?%)?[\s:\.]*(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)', 0.85),
            (r'sgst[\s:\.]*(?:@\s*\d+(?:\.\d+)?%)?[\s:\.]*(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)', 0.85),
            (r'igst[\s:\.]*(?:@\s*\d+(?:\.\d+)?%)?[\s:\.]*(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)', 0.85),
            # General tax patterns (0.7-0.8)
            (r'(?:tax|vat)[\s:\.]*(?:amount)?[\s:\.]*(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)', 0.8),
            (r'(?:service\s*tax|cess)[\s:\.]*(?:rs\.?|₹)?\s*([0-9,]+\.?\d*)', 0.7)
        ]
        
        total_tax = 0.0
        tax_confidence = 0.0
        tax_found = False
        
        for pattern, confidence in tax_patterns:
            matches = re.finditer(pattern, cleaned_text, re.IGNORECASE)
            for match in matches:
                tax_str = match.group(1).replace(',', '').replace(' ', '')
                try:
                    tax_amount = float(tax_str)
                    if 0 <= tax_amount <= 9999999:
                        total_tax += tax_amount
                        tax_confidence = max(tax_confidence, confidence)
                        tax_found = True
                except ValueError:
                    continue
        
        if tax_found:
            result['tax_amount'] = total_tax
            result['confidence_scores']['tax_amount'] = tax_confidence
        
        # Enhanced GSTIN pattern with validation
        gstin_patterns = [
            (r'(?:gstin|gst\s*no|gst\s*number)[\s:\.]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})', 0.95),
            (r'gst[\s:\.]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})', 0.9),
            (r'([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})', 0.8)  # Pattern only
        ]
        
        for pattern, confidence in gstin_patterns:
            match = re.search(pattern, cleaned_text, re.IGNORECASE)
            if match:
                gstin = match.group(1).upper()
                if _validate_gstin(gstin):
                    result['gstin'] = gstin
                    result['confidence_scores']['gstin'] = confidence
                    break
        
        # PAN pattern extraction
        pan_patterns = [
            (r'(?:pan|pan\s*no|pan\s*number)[\s:\.]*([A-Z]{5}[0-9]{4}[A-Z]{1})', 0.9),
            (r'([A-Z]{5}[0-9]{4}[A-Z]{1})', 0.7)  # Pattern only
        ]
        
        for pattern, confidence in pan_patterns:
            match = re.search(pattern, cleaned_text, re.IGNORECASE)
            if match:
                pan = match.group(1).upper()
                if _validate_pan(pan):
                    result['pan'] = pan
                    result['confidence_scores']['pan'] = confidence
                    break
        
        # Enhanced Currency detection
        currency_patterns = [
            ('INR', ['₹', 'inr', 'rs.', 'rs', 'rupees'], 0.9),
            ('USD', ['$', 'usd', 'dollars'], 0.9),
            ('EUR', ['€', 'eur', 'euros'], 0.9),
            ('GBP', ['£', 'gbp', 'pounds'], 0.9)
        ]
        
        for currency, symbols, confidence in currency_patterns:
            if any(symbol in cleaned_text.lower() for symbol in symbols):
                result['currency'] = currency
                result['confidence_scores']['currency'] = confidence
                break
        
        # Enhanced supplier name extraction
        supplier_info = _extract_supplier_info(original_text)
        if supplier_info['name']:
            result['supplier_name'] = supplier_info['name']
            result['confidence_scores']['supplier_name'] = supplier_info['confidence']
        
        if supplier_info['address']:
            result['supplier_address'] = supplier_info['address']
            result['confidence_scores']['supplier_address'] = supplier_info['address_confidence']
        
        # Calculate subtotal if total and tax are available
        if result['total_amount'] and result['tax_amount']:
            result['subtotal'] = result['total_amount'] - result['tax_amount']
            result['confidence_scores']['subtotal'] = min(
                result['confidence_scores']['total_amount'],
                result['confidence_scores']['tax_amount']
            ) * 0.9
        
        return result
        
    except Exception as e:
        raise ParsingError(f"Enhanced key-value parsing failed: {str(e)}")


def match_supplier(supplier_text: str, supplier_list: List[Dict[str, str]], threshold: float = 0.6) -> List[Dict[str, Any]]:
    """
    Enhanced supplier matching with multiple algorithms and improved scoring.
    
    Enhanced features:
    - Multiple fuzzy matching algorithms
    - Company name normalization and cleaning
    - Abbreviation and acronym handling
    - Weighted scoring based on match type
    - Better handling of Indian company suffixes
    
    Args:
        supplier_text: Extracted supplier name/text
        supplier_list: List of known suppliers with 'name' and 'supplier_name' fields
        threshold: Minimum similarity score (0-1, default: 0.6)
        
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
        # Clean and normalize supplier text
        cleaned_supplier = _normalize_company_name(supplier_text)
        
        matches = []
        
        for supplier in supplier_list:
            supplier_name = supplier.get('supplier_name') or supplier.get('name', '')
            if not supplier_name:
                continue
            
            # Clean and normalize supplier name from database
            cleaned_db_name = _normalize_company_name(supplier_name)
            
            # Skip if either name is too short after cleaning
            if len(cleaned_supplier) < 3 or len(cleaned_db_name) < 3:
                continue
            
            # Calculate multiple similarity scores
            scores = _calculate_similarity_scores(cleaned_supplier, cleaned_db_name)
            
            # Also try against original names for exact matches
            original_scores = _calculate_similarity_scores(supplier_text.lower(), supplier_name.lower())
            
            # Take the best scores
            final_scores = {
                'ratio': max(scores['ratio'], original_scores['ratio']),
                'partial': max(scores['partial'], original_scores['partial']),
                'token_sort': max(scores['token_sort'], original_scores['token_sort']),
                'token_set': max(scores['token_set'], original_scores['token_set']),
                'weighted_ratio': max(scores['weighted_ratio'], original_scores['weighted_ratio'])
            }
            
            # Enhanced weighted scoring with preference for specific match types
            combined_score = (
                final_scores['weighted_ratio'] * 0.3 +
                final_scores['token_set'] * 0.25 +
                final_scores['partial'] * 0.2 +
                final_scores['token_sort'] * 0.15 +
                final_scores['ratio'] * 0.1
            )
            
            # Bonus for exact token matches
            if _has_exact_token_match(cleaned_supplier, cleaned_db_name):
                combined_score = min(1.0, combined_score + 0.1)
            
            # Bonus for acronym matches
            if _is_acronym_match(cleaned_supplier, cleaned_db_name):
                combined_score = min(1.0, combined_score + 0.15)
            
            if combined_score >= threshold:
                matches.append({
                    'supplier_name': supplier_name,
                    'supplier_code': supplier.get('name', ''),
                    'confidence': combined_score,
                    'similarity_scores': final_scores,
                    'match_type': _determine_match_type(final_scores, cleaned_supplier, cleaned_db_name)
                })
        
        # Sort by confidence score (highest first)
        matches.sort(key=lambda x: x['confidence'], reverse=True)
        
        return matches[:10]  # Return top 10 matches
        
    except Exception as e:
        raise OCRError(f"Enhanced supplier matching failed: {str(e)}")


# Helper functions for enhanced parsing

def _clean_text_for_parsing(text: str) -> str:
    """Clean and normalize text for better parsing."""
    if not text:
        return ""
    
    # Replace common OCR errors
    text = text.replace('０', '0').replace('１', '1').replace('２', '2')  # Handle fullwidth numbers
    text = re.sub(r'[Oo](?=\d)', '0', text)  # Replace O with 0 when followed by digit
    text = re.sub(r'(?<=\d)[Oo]', '0', text)  # Replace O with 0 when preceded by digit
    text = re.sub(r'[Il](?=\d)', '1', text)  # Replace I/l with 1 when followed by digit
    
    # Normalize whitespace and line breaks
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\n', ' ').replace('\t', ' ')
    
    return text.strip()


def _is_valid_invoice_number(candidate: str) -> bool:
    """Validate if a candidate string looks like a valid invoice number."""
    if not candidate or len(candidate) < 3:
        return False
    
    # Should contain at least some alphanumeric characters
    if not re.search(r'[A-Z0-9]', candidate.upper()):
        return False
    
    # Should not be all numbers (likely an amount)
    if candidate.replace('-', '').replace('/', '').replace('\\', '').isdigit() and len(candidate) > 6:
        return False
    
    # Should not contain invalid characters
    if re.search(r'[<>{}[\]()@#$%^&*+=|;?.]', candidate):
        return False
    
    return True


def _validate_gstin(gstin: str) -> bool:
    """Basic GSTIN format validation."""
    if not gstin or len(gstin) != 15:
        return False
    
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$'
    return bool(re.match(pattern, gstin))


def _validate_pan(pan: str) -> bool:
    """Basic PAN format validation."""
    if not pan or len(pan) != 10:
        return False
    
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
    return bool(re.match(pattern, pan))


def _extract_supplier_info(text: str) -> Dict[str, Any]:
    """Extract supplier name and address from invoice text."""
    lines = text.split('\n')
    
    supplier_info = {
        'name': None,
        'address': None,
        'confidence': 0.0,
        'address_confidence': 0.0
    }
    
    # Look for company name in first few lines
    company_indicators = ['ltd', 'limited', 'pvt', 'inc', 'corp', 'llp', 'company', 'enterprises', 'industries']
    
    for i, line in enumerate(lines[:10]):  # Check first 10 lines
        line_clean = line.strip()
        if len(line_clean) < 5:
            continue
        
        line_lower = line_clean.lower()
        
        # Check if line contains company indicators
        if any(indicator in line_lower for indicator in company_indicators):
            # Additional validation
            if not re.search(r'\d{6,}', line_clean):  # Avoid lines with long numbers
                if not re.search(r'(?:invoice|bill|date|amount|total|gst)', line_lower):  # Avoid header lines
                    supplier_info['name'] = line_clean
                    supplier_info['confidence'] = 0.8
                    
                    # Try to extract address from subsequent lines
                    address_lines = []
                    for j in range(i + 1, min(i + 4, len(lines))):
                        addr_line = lines[j].strip()
                        if len(addr_line) > 5 and not re.search(r'(?:invoice|bill|date|gst)', addr_line.lower()):
                            address_lines.append(addr_line)
                    
                    if address_lines:
                        supplier_info['address'] = ', '.join(address_lines)
                        supplier_info['address_confidence'] = 0.7
                    
                    break
    
    return supplier_info


def _normalize_company_name(name: str) -> str:
    """Normalize company name for better matching."""
    if not name:
        return ""
    
    # Convert to lowercase
    name = name.lower().strip()
    
    # Remove common suffixes and prefixes
    suffixes = [
        'limited', 'ltd', 'pvt', 'private', 'inc', 'incorporated', 'corp', 'corporation',
        'llp', 'llc', 'company', 'co', 'enterprises', 'industries', 'services', 'solutions'
    ]
    
    prefixes = ['m/s', 'ms', 'messrs', 'the']
    
    # Remove prefixes
    for prefix in prefixes:
        if name.startswith(prefix + ' '):
            name = name[len(prefix):].strip()
    
    # Remove suffixes
    words = name.split()
    filtered_words = []
    for word in words:
        if word not in suffixes:
            filtered_words.append(word)
    
    name = ' '.join(filtered_words)
    
    # Remove punctuation and normalize spaces
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    
    return name.strip()


def _calculate_similarity_scores(text1: str, text2: str) -> Dict[str, float]:
    """Calculate multiple similarity scores between two texts."""
    return {
        'ratio': fuzz.ratio(text1, text2) / 100,
        'partial': fuzz.partial_ratio(text1, text2) / 100,
        'token_sort': fuzz.token_sort_ratio(text1, text2) / 100,
        'token_set': fuzz.token_set_ratio(text1, text2) / 100,
        'weighted_ratio': fuzz.WRatio(text1, text2) / 100
    }


def _has_exact_token_match(text1: str, text2: str) -> bool:
    """Check if there are exact token matches between two texts."""
    tokens1 = set(text1.split())
    tokens2 = set(text2.split())
    
    # Filter out very short tokens
    tokens1 = {t for t in tokens1 if len(t) >= 3}
    tokens2 = {t for t in tokens2 if len(t) >= 3}
    
    return bool(tokens1 & tokens2)


def _is_acronym_match(text1: str, text2: str) -> bool:
    """Check if one text could be an acronym of the other."""
    # Extract first letters of significant words
    def get_acronym(text):
        words = [w for w in text.split() if len(w) >= 3]
        return ''.join(w[0] for w in words[:5])  # Limit to 5 words
    
    acronym1 = get_acronym(text1)
    acronym2 = get_acronym(text2)
    
    # Check if either text matches the other's acronym
    return (len(acronym1) >= 3 and acronym1 in text2) or (len(acronym2) >= 3 and acronym2 in text1)


def _determine_match_type(scores: Dict[str, float], text1: str, text2: str) -> str:
    """Determine the type of match based on scores."""
    if scores['ratio'] > 0.9:
        return 'exact'
    elif scores['weighted_ratio'] > 0.8:
        return 'strong'
    elif scores['token_set'] > 0.8:
        return 'token_match'
    elif scores['partial'] > 0.8:
        return 'partial'
    elif _is_acronym_match(text1, text2):
        return 'acronym'
    else:
        return 'fuzzy'


def _normalize_date(date_str: str) -> Optional[str]:
    """
    Normalize date string to ISO format (YYYY-MM-DD).
    
    Args:
        date_str: Raw date string from invoice
        
    Returns:
        ISO formatted date string or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        # Common date formats
        formats = [
            '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
            '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
            '%Y/%m/%d', '%Y-%m-%d', '%Y.%m.%d',
            '%d %b %Y', '%d %B %Y',
            '%b %d %Y', '%B %d %Y',
            '%d %b %y', '%d %B %y',
            '%b %d %y', '%B %d %y'
        ]
        
        # Clean the date string
        date_str = re.sub(r'(?:st|nd|rd|th)', '', date_str)  # Remove ordinal suffixes
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


def test_enhanced_parsing():
    """Test enhanced parsing with various invoice formats."""
    print("Testing enhanced parsing capabilities...")
    
    # Test 1: Indian invoice with GSTIN
    indian_invoice = """
    GREENTEK SOLUTIONS PRIVATE LIMITED
    123 Tech Park, Bangalore, Karnataka 560001
    GSTIN: 29AABCG1234A1Z5
    PAN: AABCG1234A
    
    TAX INVOICE
    Invoice No: INV-2024-001
    Invoice Date: 15/03/2024
    Due Date: 30/03/2024
    
    Bill To:
    ABC Corporation Ltd
    Mumbai, Maharashtra
    
    Description          Qty    Rate      Amount
    Software License     1      50000.00  50000.00
    
    Subtotal:                            50000.00
    CGST @ 9%:                            4500.00
    SGST @ 9%:                            4500.00
    Grand Total:                         59000.00
    
    Amount in Words: Fifty Nine Thousand Only
    """
    
    # Test 2: Different format with variations
    varied_invoice = """
    ACME INDUSTRIES LLP
    Plot 456, Industrial Area
    Delhi - 110020
    GST No: 07AABCA1234B1ZX
    
    QUOTATION NO: QUO-2024-0025
    Date: 22nd March 2024
    
    To: XYZ Enterprises
    
    Item Details:
    Equipment Supply    Qty: 2    Rs. 25,000 each
    
    Total Amount: Rs. 50,000/-
    GST @ 18%: Rs. 9,000/-
    Net Payable: Rs. 59,000/-
    """
    
    try:
        # Test parsing of Indian invoice
        result1 = parse_key_values(indian_invoice)
        print(f"Indian Invoice Parsing Results:")
        print(f"  Invoice Number: {result1['invoice_number']} (confidence: {result1['confidence_scores'].get('invoice_number', 0):.2f})")
        print(f"  Date: {result1['invoice_date']} (confidence: {result1['confidence_scores'].get('invoice_date', 0):.2f})")
        print(f"  Total: {result1['total_amount']} (confidence: {result1['confidence_scores'].get('total_amount', 0):.2f})")
        print(f"  Tax: {result1['tax_amount']} (confidence: {result1['confidence_scores'].get('tax_amount', 0):.2f})")
        print(f"  GSTIN: {result1['gstin']} (confidence: {result1['confidence_scores'].get('gstin', 0):.2f})")
        print(f"  Supplier: {result1['supplier_name']} (confidence: {result1['confidence_scores'].get('supplier_name', 0):.2f})")
        
        # Test parsing of varied format
        result2 = parse_key_values(varied_invoice)
        print(f"\nVaried Invoice Parsing Results:")
        print(f"  Invoice Number: {result2['invoice_number']} (confidence: {result2['confidence_scores'].get('invoice_number', 0):.2f})")
        print(f"  Date: {result2['invoice_date']} (confidence: {result2['confidence_scores'].get('invoice_date', 0):.2f})")
        print(f"  Total: {result2['total_amount']} (confidence: {result2['confidence_scores'].get('total_amount', 0):.2f})")
        print(f"  Tax: {result2['tax_amount']} (confidence: {result2['confidence_scores'].get('tax_amount', 0):.2f})")
        print(f"  GSTIN: {result2['gstin']} (confidence: {result2['confidence_scores'].get('gstin', 0):.2f})")
        print(f"  Supplier: {result2['supplier_name']} (confidence: {result2['confidence_scores'].get('supplier_name', 0):.2f})")
        
        # Test supplier matching if rapidfuzz is available
        if HAS_RAPIDFUZZ:
            print(f"\nTesting enhanced supplier matching...")
            
            # Mock supplier database
            suppliers = [
                {'name': 'SUP001', 'supplier_name': 'Greentek Solutions Private Limited'},
                {'name': 'SUP002', 'supplier_name': 'ACME Industries LLP'},
                {'name': 'SUP003', 'supplier_name': 'ABC Corporation Ltd'},
                {'name': 'SUP004', 'supplier_name': 'Tech Solutions Pvt Ltd'},
                {'name': 'SUP005', 'supplier_name': 'Green Technologies'},
            ]
            
            # Test with extracted supplier names
            for supplier_text in [result1['supplier_name'], result2['supplier_name']]:
                if supplier_text:
                    matches = match_supplier(supplier_text, suppliers, threshold=0.5)
                    print(f"\nMatches for '{supplier_text}':")
                    for match in matches[:3]:  # Top 3 matches
                        print(f"  {match['supplier_name']} (confidence: {match['confidence']:.2f}, type: {match['match_type']})")
        
        print("\n✅ Enhanced parsing tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced parsing test failed: {str(e)}")
        return False


def test_sample_invoices():
    """Test OCR capabilities with actual sample invoices."""
    print("Testing OCR capabilities with sample invoices...")
    
    sample_dir = Path("Sample Invoices")
    if not sample_dir.exists():
        print("⚠️  Sample Invoices directory not found. Skipping real invoice tests.")
        return False
    
    # Get list of PDF files
    pdf_files = list(sample_dir.glob("*.pdf"))
    if not pdf_files:
        print("⚠️  No PDF files found in Sample Invoices directory.")
        return False
    
    print(f"Found {len(pdf_files)} sample invoices to test")
    
    # Test with first few invoices to avoid overwhelming the system
    test_files = pdf_files[:3]  # Test first 3 files
    
    for idx, pdf_file in enumerate(test_files):
        print(f"\n{'='*60}")
        print(f"Testing Invoice {idx + 1}: {pdf_file.name}")
        print(f"{'='*60}")
        
        try:
            # Step 1: Detect PDF type
            pdf_type = detect_pdf_type(pdf_file)
            print(f"📄 PDF Type: {pdf_type}")
            
            extracted_text = ""
            ocr_results = None
            
            # Step 2: Extract text based on PDF type
            if pdf_type == "searchable":
                print("📝 Extracting text from searchable PDF...")
                extracted_text = extract_text_searchable(pdf_file)
                print(f"   Extracted {len(extracted_text)} characters")
                
            elif pdf_type == "image" or pdf_type == "mixed":
                print("🖼️  Converting PDF to images for OCR...")
                
                if HAS_PDF2IMAGE and HAS_CV2 and HAS_PADDLEOCR:
                    # Convert to images
                    images = extract_images_from_pdf(pdf_file, dpi=300)
                    print(f"   Converted to {len(images)} images")
                    
                    # Perform OCR
                    print("🔍 Performing OCR with PaddleOCR...")
                    ocr_results = ocr_images_paddle(images)
                    
                    # Combine text from all pages
                    extracted_text = "\n".join([result['text'] for result in ocr_results])
                    
                    # Show OCR confidence scores
                    for result in ocr_results:
                        print(f"   Page {result['page_number']}: {result['word_count']} words, {result['confidence']:.2f} confidence")
                else:
                    print("⚠️  OCR dependencies not available. Skipping image processing.")
                    continue
            
            else:
                print("⚠️  Empty or unsupported PDF type. Skipping.")
                continue
            
            # Step 3: Parse extracted text
            if extracted_text:
                print("📊 Parsing invoice data...")
                parsed_data = parse_key_values(extracted_text)
                
                # Display parsed results
                print("\n📋 Extracted Invoice Data:")
                key_fields = ['invoice_number', 'invoice_date', 'total_amount', 'tax_amount', 'gstin', 'supplier_name']
                
                for field in key_fields:
                    value = parsed_data.get(field)
                    confidence = parsed_data['confidence_scores'].get(field, 0)
                    
                    if value is not None:
                        print(f"   {field.replace('_', ' ').title()}: {value} (confidence: {confidence:.2f})")
                    else:
                        print(f"   {field.replace('_', ' ').title()}: Not found")
                
                # Show first 200 characters of extracted text
                print(f"\n📄 Sample extracted text:")
                print(f"   {extracted_text[:200]}...")
                
            else:
                print("❌ No text extracted from invoice")
            
        except Exception as e:
            print(f"❌ Error processing {pdf_file.name}: {str(e)}")
            continue
    
    print(f"\n✅ Sample invoice testing completed!")
    return True


def test_image_preprocessing():
    """Test image preprocessing functionality."""
    print("Testing image preprocessing...")
    
    if not HAS_CV2:
        print("⚠️  OpenCV not available. Skipping image preprocessing tests.")
        return False
    
    try:
        # Create a test image (simulating a noisy invoice)
        import numpy as np
        
        # Create a sample noisy image with text-like patterns
        test_image = np.ones((400, 600, 3), dtype=np.uint8) * 240  # Light gray background
        
        # Add some noise
        noise = np.random.randint(0, 50, test_image.shape, dtype=np.uint8)
        test_image = cv2.subtract(test_image, noise)
        
        # Add some dark rectangles (simulating text)
        cv2.rectangle(test_image, (50, 50), (200, 80), (0, 0, 0), -1)
        cv2.rectangle(test_image, (50, 100), (300, 130), (0, 0, 0), -1)
        cv2.rectangle(test_image, (50, 150), (250, 180), (0, 0, 0), -1)
        
        print("   Created test image with noise and text-like patterns")
        
        # Test preprocessing
        processed = _preprocess_image_for_ocr(test_image)
        
        print(f"   Original image shape: {test_image.shape}")
        print(f"   Processed image shape: {processed.shape}")
        print(f"   Processed image type: {processed.dtype}")
        
        # Check if preprocessing worked
        if len(processed.shape) == 2:  # Should be grayscale
            print("   ✅ Successfully converted to grayscale")
        else:
            print("   ⚠️  Image still in color format")
        
        # Check if binary threshold was applied
        unique_values = np.unique(processed)
        if len(unique_values) <= 10:  # Should have limited values after threshold
            print(f"   ✅ Successfully applied binary threshold ({len(unique_values)} unique values)")
        else:
            print(f"   ⚠️  Many unique values remaining ({len(unique_values)})")
        
        print("✅ Image preprocessing test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Image preprocessing test failed: {str(e)}")
        return False


if __name__ == "__main__":
    """Run comprehensive tests when script is executed directly."""
    print("🚀 Starting comprehensive OCR pipeline tests...\n")
    
    # Test 1: Enhanced parsing capabilities
    print("=" * 60)
    print("TEST 1: Enhanced Parsing Capabilities")
    print("=" * 60)
    test_enhanced_parsing()
    
    # Test 2: Image preprocessing
    print("\n" + "=" * 60)
    print("TEST 2: Image Preprocessing")
    print("=" * 60)
    test_image_preprocessing()
    
    # Test 3: Sample invoices (if available)
    print("\n" + "=" * 60)
    print("TEST 3: Sample Invoice Processing")
    print("=" * 60)
    test_sample_invoices()
    
    print("\n🎉 All OCR pipeline tests completed!")