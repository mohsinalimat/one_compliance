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
    conditions = []
    values = []

    if filters.get("customer"):
        conditions.append("so.customer = %s")
        values.append(filters["customer"])

    if filters.get("company"):
        conditions.append("so.company = %s")
        values.append(filters["company"])

    if filters.get("territory"):
        # Include all child territories
        territory = frappe.get_doc("Territory", filters["territory"])
        territories = [filters["territory"]]
        if territory.is_group:
            territories = [d.name for d in frappe.get_all("Territory", filters={"lft": [">=", territory.lft], "rgt": ["<=", territory.rgt]})]
        conditions.append("cust.territory IN ({})".format(", ".join(["%s"] * len(territories))))
        values.extend(territories)

    if filters.get("customer_group"):
        # Include all child customer groups
        customer_group = frappe.get_doc("Customer Group", filters["customer_group"])
        customer_groups = [filters["customer_group"]]
        if customer_group.is_group:
            customer_groups = [d.name for d in frappe.get_all("Customer Group", filters={"lft": [">=", customer_group.lft], "rgt": ["<=", customer_group.rgt]})]
        conditions.append("cust.customer_group IN ({})".format(", ".join(["%s"] * len(customer_groups))))
        values.extend(customer_groups)

    return " AND ".join(conditions), values

def get_data(filters):
    today = getdate(filters.get("report_date") or nowdate())
    data = []

    # Use transaction_date for all date filtering even if filter field is called order_date
    date_field = "transaction_date"

    # Build date filter condition for transaction_date
    date_condition = ""
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    values = []

    if filters.get("ageing_based_on") == "Posting Date" and from_date and to_date:
        date_condition = "AND so.transaction_date BETWEEN %s AND %s"
        values.extend([from_date, to_date])

    elif filters.get("ageing_based_on") == "Due Date" and from_date and to_date:
        date_condition = "AND ps.due_date BETWEEN %s AND %s"
        values.extend([from_date, to_date])


    # Build conditions for other filters (customer, company, territory, etc)
    conditions, extra_values = get_conditions(filters)

    # Workflow states filter
    workflow_states = ["Proforma Invoice"]
    if filters.get("include_invoiced"):
        workflow_states.append("Invoiced")
    if filters.get("include_paid"):
        workflow_states.append("Paid")

    workflow_condition = f"AND so.workflow_state IN ({', '.join(['%s'] * len(workflow_states))})"

    # Compose final list of values matching placeholders
    # First value for DATEDIFF (today), then workflow states, then date filter, then other filters
    values = [today] + workflow_states + values + extra_values

    query = f"""
        SELECT
            so.transaction_date AS posting_date,
            'Customer' AS party_type,
            so.customer,
            soi.cost_center,
            ps.due_date AS due_date,
            'Sales Order' AS voucher_type,
            so.name AS voucher_no,
            so.grand_total,
            so.advance_paid AS paid_amount,
            (so.grand_total - so.advance_paid) AS outstanding_amount,
            DATEDIFF(%s, so.{date_field}) AS age,
            so.currency,
            cust.territory,
            cust.customer_group,
            cust.customer_primary_contact AS customer_contact
        FROM `tabSales Order` so
        LEFT JOIN `tabSales Order Item` soi ON soi.parent = so.name
        LEFT JOIN `tabCustomer` cust ON cust.name = so.customer
        LEFT JOIN `tabPayment Schedule` ps ON ps.parent = so.name
        WHERE so.docstatus = 1
        {workflow_condition}
        {date_condition}
        {f"AND {conditions}" if conditions else ""}
        GROUP BY so.name
    """

    results = frappe.db.sql(query, values, as_dict=True)

    # Process ageing ranges (same as before)
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
