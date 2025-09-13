# Copyright (c) 2025, GreentekIndia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InvoiceProcessingJob(Document):
	"""
	Controller for Invoice Processing Job DocType.
	Handles the lifecycle of invoice processing from upload to posting.
	"""
	
	def before_insert(self):
		"""Set default values before inserting the document."""
		self.set_naming_series()
		self.set_submitted_details()
	
	def validate(self):
		"""Validate the document before saving."""
		self.set_naming_series()
		self.set_submitted_details()
		self.validate_status_transition()
	
	def set_naming_series(self):
		"""Set naming series if not already set."""
		if not self.naming_series:
			self.naming_series = "IPJ-.YYYY.-"
	
	def set_submitted_details(self):
		"""Set submitted_by and submitted_on if not already set."""
		if not self.submitted_by:
			self.submitted_by = frappe.session.user
		if not self.submitted_on:
			self.submitted_on = frappe.utils.now()
	
	def validate_status_transition(self):
		"""Validate status transitions according to workflow."""
		if self.is_new():
			return
		
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		
		valid_transitions = {
			"Draft": ["Pending Review"],
			"Pending Review": ["Approved", "Rejected"],
			"Approved": ["Posted", "Pending Review"],
			"Rejected": [],  # Final state
			"Posted": []  # Final state
		}
		
		old_status = old_doc.status
		new_status = self.status
		
		if old_status != new_status:
			if new_status not in valid_transitions.get(old_status, []):
				frappe.throw(f"Invalid status transition from {old_status} to {new_status}")
	
	def on_submit(self):
		"""Actions to perform when document is submitted."""
		if self.status == "Draft":
			self.status = "Pending Review"
		self.add_review_entry("Document submitted for review")
	
	def on_cancel(self):
		"""Actions to perform when document is cancelled."""
		self.status = "Draft"
		self.add_review_entry("Document cancelled")
	
	def add_review_entry(self, notes):
		"""Add a review entry to track status changes."""
		self.append("invoice_reviews", {
			"reviewed_by": frappe.session.user,
			"review_notes": notes,
			"approval_status": "Pending"
		})
	
	@frappe.whitelist()
	def approve_invoice(self, review_notes=None):
		"""Approve the invoice for posting."""
		if self.status != "Pending Review":
			frappe.throw("Invoice must be in Pending Review status to approve")
		
		self.status = "Approved"
		self.add_review_entry(review_notes or "Invoice approved")
		self.save()
		
		frappe.msgprint("Invoice has been approved", indicator="green")
	
	@frappe.whitelist()
	def reject_invoice(self, review_notes=None):
		"""Reject the invoice and mark as rejected."""
		if self.status != "Pending Review":
			frappe.throw("Invoice must be in Pending Review status to reject")
		
		self.status = "Rejected"
		self.add_review_entry(review_notes or "Invoice rejected")
		self.save()
		
		frappe.msgprint("Invoice has been rejected", indicator="red")
	
	@frappe.whitelist()
	def post_to_erp(self):
		"""Post the approved invoice to ERPNext."""
		if self.status != "Approved":
			frappe.throw("Invoice must be approved before posting")
		
		# TODO: Implement ERPNext integration logic here
		# This will be done in a later phase
		
		self.status = "Posted"
		self.add_review_entry("Invoice posted to ERPNext")
		self.save()
		
		frappe.msgprint("Invoice has been posted to ERP", indicator="green")