"""
Invoice Manager Processing Module

This module contains the core OCR processing pipeline and integration layers
for automated invoice data extraction.

Modules:
- pipeline: Framework-agnostic OCR processing functions
- client: Frappe integration layer (to be implemented)
"""

from .pipeline import (
    check_dependencies,
    detect_pdf_type,
    extract_text_searchable,
    extract_images_from_pdf,
    ocr_images_paddle,
    extract_tables_with_camelot,
    parse_key_values,
    match_supplier,
    PIPELINE_VERSION,
    OCRError,
    PDFError,
    ImageProcessingError,
    ParsingError
)

__all__ = [
    'check_dependencies',
    'detect_pdf_type', 
    'extract_text_searchable',
    'extract_images_from_pdf',
    'ocr_images_paddle',
    'extract_tables_with_camelot',
    'parse_key_values',
    'match_supplier',
    'PIPELINE_VERSION',
    'OCRError',
    'PDFError',
    'ImageProcessingError',
    'ParsingError'
]