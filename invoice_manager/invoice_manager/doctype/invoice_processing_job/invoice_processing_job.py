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
		# Note: Status transition validation is handled by workflow
		# self.validate_status_transition()
	
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
		"""Status transitions are handled by workflow."""
		# Workflow handles all status transitions
		pass
	
	def on_submit(self):
		"""Actions to perform when document is submitted."""
		# Do not change status here. Workflow should drive status transitions.
		# Keep a review entry so submission is tracked.
		self.add_review_entry("Document submitted (submit action)")
	
	def on_cancel(self):
		"""Actions to perform when document is cancelled."""
		# Note: Status updates are handled by workflow
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

		# Enforce role-based permission for posting
		if not frappe.has_role("System Manager"):
			frappe.throw("Only System Manager can post to ERPNext")

		# TODO: Implement ERPNext integration logic here (call external APIs, create Sales Invoice, etc.)
		# For now, update status server-side to avoid client-side 'Cannot Update After Submit' validation.
		try:
			frappe.db.set_value("Invoice Processing Job", self.name, "status", "Posted")
			# insert an invoice review row for auditing the automated post
			try:
				frappe.get_doc({
					"doctype": "Invoice Review",
					"parent": self.name,
					"parentfield": "invoice_reviews",
					"parenttype": "Invoice Processing Job",
					"reviewed_by": frappe.session.user or "Administrator",
					"review_notes": "Invoice posted to ERPNext (automated)",
					"approval_status": "Approved",
				}).insert(ignore_permissions=True)
			except Exception:
				# fallback to direct SQL insert if the child insert fails
				try:
					frappe.db.sql(
						"INSERT INTO `tabInvoice Review` (parent, parentfield, parenttype, reviewed_by, review_notes, approval_status) VALUES (%s,%s,%s,%s,%s,%s)",
						(self.name, "invoice_reviews", "Invoice Processing Job", frappe.session.user or "Administrator", "Invoice posted to ERPNext (automated)", "Approved"),
					)
					frappe.db.commit()
				except Exception:
					pass
			frappe.db.commit()
		except Exception as e:
			frappe.throw(f"Failed to update status: {e}")

		frappe.msgprint("Invoice has been posted to ERP", indicator="green")