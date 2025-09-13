import frappe


def run_check():
    dt = "Invoice Processing Job"
    result_pending = frappe.get_all(
        dt,
        filters=[
            ["status", "=", "Pending Review"],
            ["docstatus", "!=", 0],
        ],
        fields=["name", "docstatus", "status"],
        limit_page_length=1000,
    )

    result_rejected = frappe.get_all(
        dt,
        filters=[
            ["status", "=", "Rejected"],
            ["docstatus", "!=", 0],
        ],
        fields=["name", "docstatus", "status"],
        limit_page_length=1000,
    )

    print('Pending Review mismatches:')
    print(result_pending)
    print('Rejected mismatches:')
    print(result_rejected)


def print_sample_docs():
    docs = frappe.get_all(
        "Invoice Processing Job",
        fields=["name", "status", "docstatus"],
        limit_page_length=20,
    )
    print('Sample Invoice Processing Job docs:')
    print(docs)
