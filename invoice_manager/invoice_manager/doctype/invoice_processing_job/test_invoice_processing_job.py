# Copyright (c) 2025, GreentekIndia and Contributors
# See license.txt

import frappe
import unittest


class TestInvoiceProcessingJob(unittest.TestCase):
	"""Test cases for Invoice Processing Job DocType."""
	
	def setUp(self):
		"""Set up test data."""
		self.test_user = "test@example.com"
		if not frappe.db.exists("User", self.test_user):
			user = frappe.get_doc({
				"doctype": "User",
				"email": self.test_user,
				"first_name": "Test",
				"last_name": "User"
			})
			user.insert(ignore_permissions=True)
	
	def test_create_invoice_processing_job(self):
		"""Test creating a new Invoice Processing Job."""
		doc = frappe.get_doc({
			"doctype": "Invoice Processing Job",
			"submitted_by": self.test_user,
			"invoice_file": "/test/invoice.pdf",
			"status": "Draft"
		})
		doc.insert()
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.submitted_by, self.test_user)
	
	def test_status_transition_validation(self):
		"""Test that invalid status transitions are blocked."""
		doc = frappe.get_doc({
			"doctype": "Invoice Processing Job",
			"submitted_by": self.test_user,
			"invoice_file": "/test/invoice.pdf",
			"status": "Draft"
		})
		doc.insert()
		
		# Try invalid transition from Draft to Posted
		doc.status = "Posted"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
	
	def tearDown(self):
		"""Clean up test data."""
		frappe.db.rollback()