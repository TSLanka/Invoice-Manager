"""
Frappe Integration Client for OCR Processing

This module provides the integration layer between the framework-agnostic
OCR pipeline and the Frappe framework. It handles background job enqueueing,
progress tracking, and database updates.

Key Features:
- Async job processing using Frappe's background job system
- Progress tracking and status updates
- File access and temporary file management
- Error handling and logging integration
- Frappe permission integration

Author: Invoice Manager Development Team
Version: 1.0.0
"""

import frappe
import json
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, List
from frappe.utils import now, get_files_path, get_site_path
from frappe.core.doctype.file.file import get_file_path
import tempfile
import os

# Import the framework-agnostic pipeline
from invoice_manager.processing.pipeline import (
    detect_pdf_type,
    extract_text_searchable,
    extract_images_from_pdf,
    ocr_images_paddle,
    extract_tables_with_camelot,
    parse_key_values,
    match_supplier,
    check_dependencies,
    PIPELINE_VERSION,
    OCRError,
    PDFError,
    ImageProcessingError,
    ParsingError
)


def enqueue_extraction_job(job_id: str, priority: str = "medium") -> str:
    """
    Enqueue an OCR extraction job for background processing.
    
    Args:
        job_id: Invoice Processing Job document name
        priority: Job priority ("low", "medium", "high")
        
    Returns:
        str: Frappe job ID for tracking
        
    Raises:
        frappe.ValidationError: If job cannot be enqueued
    """
    try:
        # Validate job exists
        if not frappe.db.exists("Invoice Processing Job", job_id):
            frappe.throw(f"Invoice Processing Job {job_id} not found")
        
        # Check if job is already processing
        job_doc = frappe.get_doc("Invoice Processing Job", job_id)
        if job_doc.status in ["Processing", "Posted"]:
            frappe.throw(f"Job {job_id} is already in status: {job_doc.status}")
        
        # Enqueue the background job
        frappe_job = frappe.enqueue(
            method='invoice_manager.processing.client.process_extraction_job',
            queue='long',  # Use long queue for OCR processing
            timeout=1800,  # 30 minutes timeout
            job_id=job_id,
            is_async=True,
            priority=priority,
            job_name=f"ocr_extraction_{job_id}"
        )
        
        # Update job status
        frappe.db.set_value("Invoice Processing Job", job_id, {
            "status": "Processing",
            "extraction_log": f"OCR extraction job enqueued at {now()}\\nJob ID: {frappe_job}\\nPipeline Version: {PIPELINE_VERSION}"
        })
        frappe.db.commit()
        
        frappe.logger().info(f"Enqueued OCR extraction job for {job_id}: {frappe_job}")
        
        return frappe_job
        
    except Exception as e:
        frappe.logger().error(f"Failed to enqueue OCR job for {job_id}: {str(e)}")
        raise


def process_extraction_job(job_id: str) -> Dict[str, Any]:
    """
    Background job to process invoice OCR extraction.
    
    Args:
        job_id: Invoice Processing Job document name
        
    Returns:
        Dict: Processing results with extraction data
        
    Note: This function runs in background and updates the database directly
    """
    log_entries = [f"Starting OCR extraction for job {job_id} at {now()}"]
    
    try:
        # Get the job document
        job_doc = frappe.get_doc("Invoice Processing Job", job_id)
        
        if not job_doc.invoice_file:
            raise ValueError("No invoice file attached to process")
        
        log_entries.append(f"Processing file: {job_doc.invoice_file}")
        
        # Get file path
        file_path = get_file_path(job_doc.invoice_file)
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Invoice file not found: {job_doc.invoice_file}")
        
        log_entries.append(f"File path resolved: {file_path}")
        
        # Check dependencies
        deps = check_dependencies()
        missing_deps = [dep for dep, available in deps.items() if not available]
        if missing_deps:
            log_entries.append(f"Warning: Missing dependencies: {missing_deps}")
        
        # Step 1: Analyze PDF
        log_entries.append("Step 1: Analyzing PDF structure...")
        try:
            pdf_info = detect_pdf_type(file_path)
            log_entries.append(f"PDF analysis: {pdf_info}")
        except PDFError as e:
            # Fall back to treating as scanned if analysis fails
            pdf_info = {"is_searchable": False, "page_count": 1}
            log_entries.append(f"PDF analysis failed, treating as scanned: {str(e)}")
        
        extracted_text = ""
        ocr_confidence = 0.0
        
        # Step 2: Extract text based on PDF type
        if pdf_info.get("is_searchable", False):
            log_entries.append("Step 2: Extracting text from searchable PDF...")
            try:
                extracted_text = extract_text_searchable(file_path)
                ocr_confidence = 0.95  # High confidence for searchable PDFs
                log_entries.append(f"Extracted {len(extracted_text)} characters from searchable PDF")
            except Exception as e:
                log_entries.append(f"Text extraction failed: {str(e)}")
                # Fall back to OCR
                pdf_info["is_searchable"] = False
        
        # Step 3: OCR processing for scanned PDFs
        if not pdf_info.get("is_searchable", False):
            log_entries.append("Step 3: Performing OCR on scanned document...")
            try:
                # Convert to images
                images = extract_images_from_pdf(file_path)
                log_entries.append(f"Converted PDF to {len(images)} images")
                
                # Perform OCR
                ocr_results = ocr_images_paddle(images)
                
                # Combine text from all pages
                page_texts = []
                confidences = []
                for result in ocr_results:
                    page_texts.append(result['text'])
                    confidences.append(result['confidence'])
                
                extracted_text = "\\n\\n".join(page_texts)
                ocr_confidence = sum(confidences) / len(confidences) if confidences else 0.0
                
                log_entries.append(f"OCR completed. Extracted {len(extracted_text)} characters with {ocr_confidence:.2f} confidence")
                
            except (ImageProcessingError, OCRError) as e:
                log_entries.append(f"OCR processing failed: {str(e)}")
                extracted_text = f"OCR processing failed: {str(e)}"
                ocr_confidence = 0.0
        
        # Step 4: Parse structured data
        log_entries.append("Step 4: Parsing structured data...")
        try:
            parsed_data = parse_key_values(extracted_text)
            log_entries.append(f"Parsed data: {len([k for k, v in parsed_data.items() if v is not None])} fields extracted")
        except ParsingError as e:
            log_entries.append(f"Data parsing failed: {str(e)}")
            parsed_data = {"error": str(e)}
        
        # Step 5: Supplier matching
        log_entries.append("Step 5: Matching suppliers...")
        supplier_matches = []
        try:
            if parsed_data.get("supplier_name"):
                # Get suppliers from ERPNext
                suppliers = frappe.get_all("Supplier", 
                    fields=["name", "supplier_name"], 
                    limit=100
                )
                
                supplier_matches = match_supplier(
                    parsed_data["supplier_name"], 
                    suppliers, 
                    threshold=0.6
                )
                log_entries.append(f"Found {len(supplier_matches)} supplier matches")
            else:
                log_entries.append("No supplier name extracted for matching")
        except Exception as e:
            log_entries.append(f"Supplier matching failed: {str(e)}")
        
        # Step 6: Update database
        log_entries.append("Step 6: Updating database...")
        update_data = {
            "ocr_raw_text": extracted_text,
            "parsed_json": json.dumps(parsed_data, indent=2),
            "extraction_version": PIPELINE_VERSION,
            "extraction_log": "\\n".join(log_entries),
            "status": "Pending Review"
        }
        
        # Update the document
        frappe.db.set_value("Invoice Processing Job", job_id, update_data)
        
        # Update supplier matches if found
        if supplier_matches:
            job_doc.reload()
            job_doc.supplier_matches = []  # Clear existing matches
            for match in supplier_matches[:5]:  # Limit to top 5 matches
                job_doc.append("supplier_matches", {
                    "supplier": match["supplier_code"],
                    "supplier_name": match["supplier_name"],
                    "confidence_score": match["confidence"]
                })
            job_doc.save(ignore_permissions=True)
        
        frappe.db.commit()
        log_entries.append(f"OCR extraction completed successfully at {now()}")
        
        # Final log update
        frappe.db.set_value("Invoice Processing Job", job_id, 
            "extraction_log", "\\n".join(log_entries))
        frappe.db.commit()
        
        frappe.logger().info(f"OCR extraction completed for job {job_id}")
        
        return {
            "success": True,
            "job_id": job_id,
            "extracted_text_length": len(extracted_text),
            "ocr_confidence": ocr_confidence,
            "parsed_fields": len([k for k, v in parsed_data.items() if v is not None]),
            "supplier_matches": len(supplier_matches)
        }
        
    except Exception as e:
        error_msg = f"OCR extraction failed: {str(e)}"
        log_entries.append(f"ERROR: {error_msg}")
        log_entries.append(f"Traceback: {traceback.format_exc()}")
        
        # Update job with error status
        try:
            frappe.db.set_value("Invoice Processing Job", job_id, {
                "status": "Draft",  # Reset to draft for retry
                "extraction_log": "\\n".join(log_entries)
            })
            frappe.db.commit()
        except Exception:
            pass
        
        frappe.logger().error(f"OCR extraction failed for job {job_id}: {str(e)}")
        
        return {
            "success": False,
            "job_id": job_id,
            "error": error_msg
        }


def get_extraction_status(job_id: str) -> Dict[str, Any]:
    """
    Get the current status of an OCR extraction job.
    
    Args:
        job_id: Invoice Processing Job document name
        
    Returns:
        Dict: Current status and progress information
    """
    try:
        job_doc = frappe.get_doc("Invoice Processing Job", job_id)
        
        return {
            "job_id": job_id,
            "status": job_doc.status,
            "extraction_version": job_doc.extraction_version,
            "has_raw_text": bool(job_doc.ocr_raw_text),
            "has_parsed_data": bool(job_doc.parsed_json),
            "supplier_matches": len(job_doc.supplier_matches or []),
            "last_updated": job_doc.modified
        }
        
    except Exception as e:
        frappe.logger().error(f"Failed to get extraction status for {job_id}: {str(e)}")
        return {
            "job_id": job_id,
            "status": "Error",
            "error": str(e)
        }


@frappe.whitelist()
def trigger_extraction(job_id: str) -> Dict[str, Any]:
    """
    API endpoint to trigger OCR extraction for a job.
    
    Args:
        job_id: Invoice Processing Job document name
        
    Returns:
        Dict: Response with job status
    """
    try:
        # Check permissions
        if not frappe.has_permission("Invoice Processing Job", "write", job_id):
            frappe.throw("Insufficient permissions to trigger extraction")
        
        # Enqueue the job
        frappe_job_id = enqueue_extraction_job(job_id)
        
        return {
            "success": True,
            "message": "OCR extraction started",
            "job_id": job_id,
            "frappe_job_id": frappe_job_id
        }
        
    except Exception as e:
        frappe.logger().error(f"Failed to trigger extraction for {job_id}: {str(e)}")
        return {
            "success": False,
            "message": str(e),
            "job_id": job_id
        }


# TODO: Add progress tracking for long-running OCR jobs
# TODO: Implement retry logic for failed extractions
# TODO: Add support for batch processing multiple files
# TODO: Optimize memory usage for large PDF files