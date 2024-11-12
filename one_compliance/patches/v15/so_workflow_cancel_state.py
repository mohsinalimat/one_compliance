import frappe


def execute():
    if frappe.db.exists("Sales Order", {"docstatus": "2"}) and hasattr(
        frappe.new_doc("Sales Order"), "workflow_state"
    ):
        frappe.db.sql(
            """UPDATE `tabSales Order` SET workflow_state = 'Cancelled' WHERE docstatus=2"""
        )
