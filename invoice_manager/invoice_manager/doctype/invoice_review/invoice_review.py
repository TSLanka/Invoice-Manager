# Copyright (c) 2025, GreentekIndia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InvoiceReview(Document):
	"""
	Controller for Invoice Review child table DocType.
	Tracks review history and approval decisions.
	"""
	
	def validate(self):
		"""Validate the review entry."""
		self.set_reviewer()
	
	def set_reviewer(self):
		"""Ensure reviewer is set to current user if not provided."""
		if not self.reviewed_by:
			self.reviewed_by = frappe.session.user