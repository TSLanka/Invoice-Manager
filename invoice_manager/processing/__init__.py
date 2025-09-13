"""
Invoice Manager Processing Module

This module contains the core OCR processing pipeline and integration layers
for automated invoice data extraction.

Modules:
- pipeline: Framework-agnostic OCR processing functions
- client: Frappe integration layer for background jobs and API endpoints
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

# Import client functions for Frappe integration
try:
    from .client import (
        enqueue_extraction_job,
        process_extraction_job,
        get_extraction_status,
        trigger_extraction
    )
    HAS_CLIENT = True
except ImportError:
    # Handle case where Frappe is not available
    HAS_CLIENT = False

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

if HAS_CLIENT:
    __all__.extend([
        'enqueue_extraction_job',
        'process_extraction_job', 
        'get_extraction_status',
        'trigger_extraction'
    ])