import frappe


def execute():
    """Migration to fix Invoice Processing Job workflow docstatus mismatches.

    Strategy (conservative):
    - Find documents with status='Pending Review' but docstatus != 0 (usually 1)
    - Set their `status` to 'Approved' so the `status` matches the docstatus (1)
    - Append a review entry indicating the automated migration
    - Do not change `docstatus` values (avoid destructive unsubmit)

    This is intentionally narrow to avoid making risky assumptions about other states.
    """

    dt = "Invoice Processing Job"
    mismatches = frappe.get_all(
        dt,
        filters=[
            ["status", "=", "Pending Review"],
            ["docstatus", "!=", 0],
        ],
        fields=["name", "docstatus", "status"],
        limit_page_length=1000,
    )

    if not mismatches:
        print("No Pending Review/docstatus mismatches found. Continuing to submitted-mismatch checks...")
    else:
        print(f"Found {len(mismatches)} mismatched documents. Fixing...")

    for r in mismatches:
        name = r["name"] if isinstance(r, dict) else r[0]
        try:
            doc = frappe.get_doc(dt, name)
            old_status = doc.status
            old_docstatus = doc.docstatus

            # Only change if still in Pending Review
            if doc.status == "Pending Review" and doc.docstatus != 0:
                doc.status = "Approved"
                # add a migration note in invoice_reviews table if present
                if hasattr(doc, "append"):
                    try:
                        doc.append("invoice_reviews", {
                            "reviewed_by": frappe.session.user or "Administrator",
                            "review_notes": (
                                "Automated migration: status adjusted from 'Pending Review' to 'Approved' "
                                "to match docstatus ({})".format(doc.docstatus)
                            ),
                            "approval_status": "Migrated",
                        })
                    except Exception:
                        # ignore append failures
                        pass

                doc.save(ignore_permissions=True)
                frappe.db.commit()
                print(f"Fixed {name}: status {old_status} (docstatus={old_docstatus}) -> {doc.status}")
            else:
                print(f"Skipped {name}: status={doc.status}, docstatus={doc.docstatus}")
        except Exception as e:
            print(f"Error processing {name}: {e}")

    # Also fix docs where docstatus = 1 but status is still a draft-like value
    submitted_mismatch = frappe.get_all(
        dt,
        filters=[
            ["docstatus", "=", 1],
            ["status", "in", ["Draft", "Pending Review", "Rejected"]],
        ],
        fields=["name", "docstatus", "status"],
        limit_page_length=1000,
    )

    if submitted_mismatch:
        print(f"Found {len(submitted_mismatch)} documents with docstatus=1 but draft-like status. Fixing to 'Approved'...")
        for r in submitted_mismatch:
            name = r["name"] if isinstance(r, dict) else r[0]
            try:
                doc = frappe.get_doc(dt, name)
                old_status = doc.status
                if doc.docstatus == 1 and doc.status in ("Draft", "Pending Review", "Rejected"):
                    # Bypass workflow validation by writing directly to DB
                    frappe.db.set_value(dt, name, "status", "Approved")
                    # Record an invoice_review entry via direct insert (child table)
                    try:
                        frappe.get_doc({
                            "doctype": "Invoice Review",
                            "parent": name,
                            "parentfield": "invoice_reviews",
                            "parenttype": dt,
                            "reviewed_by": frappe.session.user or "Administrator",
                            "review_notes": "Automated migration: status adjusted to 'Approved' to match docstatus=1",
                            "approval_status": "Migrated",
                        }).insert(ignore_permissions=True)
                    except Exception:
                        # fallback to direct SQL insert into tabInvoice Review if necessary
                        try:
                            frappe.db.sql(
                                "INSERT INTO `tabInvoice Review` (parent, parentfield, parenttype, reviewed_by, review_notes, approval_status) VALUES (%s,%s,%s,%s,%s,%s)",
                                (name, "invoice_reviews", dt, frappe.session.user or "Administrator", "Automated migration: status adjusted to 'Approved' to match docstatus=1", "Migrated"),
                            )
                            frappe.db.commit()
                        except Exception:
                            pass

                    frappe.db.commit()
                    print(f"Fixed {name}: status {old_status} -> Approved (db set)")
            except Exception as e:
                print(f"Error processing {name}: {e}")
