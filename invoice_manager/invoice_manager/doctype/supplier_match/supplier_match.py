# Copyright (c) 2025, GreentekIndia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SupplierMatch(Document):
	"""
	Controller for Supplier Match child table DocType.
	Stores supplier matching results from AI/ML processing.
	"""
	
	def validate(self):
		"""Validate the supplier match."""
		self.validate_confidence_score()
		self.set_matched_on()
	
	def validate_confidence_score(self):
		"""Validate that confidence score is between 0 and 1."""
		if self.confidence_score is not None:
			if self.confidence_score < 0 or self.confidence_score > 1:
				frappe.throw("Confidence score must be between 0 and 1")
	
	def set_matched_on(self):
		"""Set matched_on to current datetime if not provided."""
		if not self.matched_on:
			self.matched_on = frappe.utils.now()