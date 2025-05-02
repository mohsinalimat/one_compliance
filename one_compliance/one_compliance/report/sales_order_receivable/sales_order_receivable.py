# Copyright (c) 2025, efeone and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, nowdate

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)
    chart = get_chart_data(data)

    return columns, data, None, chart

def get_columns():
    return [
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Party Type", "fieldname": "party_type", "fieldtype": "Data", "width": 100},
        {"label": "Party", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
        {"label": "Cost Center", "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 130},
        {"label": "Voucher Type", "fieldname": "voucher_type", "fieldtype": "Data", "width": 100},
        {"label": "Voucher No", "fieldname": "voucher_no", "fieldtype": "Link", "options": "Sales Order", "width": 140},
        {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 100},
        {"label": "Sales Order Amount", "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
        {"label": "Paid Amount", "fieldname": "paid_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Outstanding Amount", "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 140},
        {"label": "Age (Days)", "fieldname": "age", "fieldtype": "Int", "width": 90},
        {"label": "0-30", "fieldname": "range1", "fieldtype": "Currency", "width": 100},
        {"label": "31-60", "fieldname": "range2", "fieldtype": "Currency", "width": 100},
        {"label": "61-90", "fieldname": "range3", "fieldtype": "Currency", "width": 100},
        {"label": "91-120", "fieldname": "range4", "fieldtype": "Currency", "width": 100},
        {"label": "121-Above", "fieldname": "range5", "fieldtype": "Currency", "width": 110},
        {"label": "Currency", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
        {"label": "Territory", "fieldname": "territory", "fieldtype": "Link", "options": "Territory", "width": 120},
        {"label": "Customer Group", "fieldname": "customer_group", "fieldtype": "Link", "options": "Customer Group", "width": 140},
        {"label": "Customer Contact", "fieldname": "customer_contact", "fieldtype": "Link", "options": "Contact", "width": 150},
    ]

def get_conditions(filters):
    conditions = ""
    values = []

    if filters.get("customer"):
        conditions += " AND so.customer = %s"
        values.append(filters["customer"])

    if filters.get("territory"):
        conditions += " AND cust.territory = %s"
        values.append(filters["territory"])

    if filters.get("customer_group"):
        conditions += " AND cust.customer_group = %s"
        values.append(filters["customer_group"])

    return conditions, values

def get_data(filters):
    today = getdate(filters.get("report_date") or nowdate())
    data = []

    conditions, values = get_conditions(filters)
    values = [today] + values  # Prepend for DATEDIFF

    # Set workflow state condition
    workflow_states = ["Proforma Invoice"]
    if filters.get("include_invoiced"):
        workflow_states.append("Invoiced")
    if filters.get("include_paid"):
        workflow_states.append("Paid")

    workflow_condition = f"AND so.workflow_state IN ({', '.join(['%s'] * len(workflow_states))})"
    values.extend(workflow_states)

    query = f"""
        SELECT
            so.transaction_date AS posting_date,
            'Customer' AS party_type,
            so.customer,
            soi.cost_center,
            'Sales Order' AS voucher_type,
            so.name AS voucher_no,
            so.delivery_date AS due_date,
            so.grand_total,
            so.advance_paid AS paid_amount,
            (so.grand_total - so.advance_paid) AS outstanding_amount,
            DATEDIFF(%s, so.transaction_date) AS age,
            so.currency,
            cust.territory,
            cust.customer_group,
            cust.customer_primary_contact AS customer_contact
        FROM `tabSales Order` so
        LEFT JOIN `tabSales Order Item` soi ON soi.parent = so.name
        LEFT JOIN `tabCustomer` cust ON cust.name = so.customer
        LEFT JOIN `tabDynamic Link` dl ON dl.link_doctype = 'Customer' AND dl.link_name = so.customer AND dl.parenttype = 'Contact'
        LEFT JOIN `tabContact` c ON c.name = dl.parent AND c.is_primary_contact = 1
        WHERE so.docstatus = 1
        {workflow_condition}
        {conditions}
        GROUP BY so.name
    """

    results = frappe.db.sql(query, values, as_dict=True)

    for row in results:
        age = row.age or 0
        row.range1 = row.range2 = row.range3 = row.range4 = row.range5 = 0

        if age <= 30:
            row.range1 = row.outstanding_amount
        elif age <= 60:
            row.range2 = row.outstanding_amount
        elif age <= 90:
            row.range3 = row.outstanding_amount
        elif age <= 120:
            row.range4 = row.outstanding_amount
        else:
            row.range5 = row.outstanding_amount

        data.append(row)

    return data

def get_chart_data(data):
    chart = {
        "data": {
            "labels": ["0-30", "31-60", "61-90", "91-120", "121-Above"],
            "datasets": [
                {
                    "name": "Outstanding Amount",
                    "values": [
                        sum(row.get("range1", 0) for row in data),
                        sum(row.get("range2", 0) for row in data),
                        sum(row.get("range3", 0) for row in data),
                        sum(row.get("range4", 0) for row in data),
                        sum(row.get("range5", 0) for row in data),
                    ]
                }
            ]
        },
        "type": "percentage"
    }
    return chart
