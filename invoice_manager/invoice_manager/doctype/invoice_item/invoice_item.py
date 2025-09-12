# Copyright (c) 2025, GreentekIndia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InvoiceItem(Document):
	"""
	Controller for Invoice Item child table DocType.
	Represents individual line items in an invoice.
	"""
	
	def validate(self):
		"""Validate the invoice item."""
		self.validate_qty_and_rate()
		self.calculate_amount()
	
	def validate_qty_and_rate(self):
		"""Validate that quantity and rate are positive."""
		if self.qty is not None and self.qty < 0:
			frappe.throw("Quantity cannot be negative")
		
		if self.rate is not None and self.rate < 0:
			frappe.throw("Rate cannot be negative")
	
	def calculate_amount(self):
		"""Calculate the amount based on quantity and rate."""
		if self.qty and self.rate:
			self.amount = self.qty * self.rate
		else:
			self.amount = 0