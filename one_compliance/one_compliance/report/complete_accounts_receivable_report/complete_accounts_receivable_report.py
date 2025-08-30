# Copyright (c) 2025, efeone and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, nowdate

def execute(filters: dict | None = None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data

def get_columns() -> list[dict]:
	return [
		{"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 200},
		{"label": "Customer Group", "fieldname": "customer_group", "fieldtype": "Link", "options": "Customer Group", "width": 150},
		{"label": "Voucher Type", "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
		{"label": "Voucher No", "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 200},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": "Amount", "fieldname": "grand_total", "fieldtype": "Currency", "width": 150},
		{"label": "Paid Amount", "fieldname": "paid_amount", "fieldtype": "Currency", "width": 150},
		{"label": "Outstanding Amount", "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 180},
	]

def get_conditions(filters: dict) -> tuple[str, list]:
	conditions = []
	vals = []

	if filters.get("company"):
		conditions.append("so.company = %s")
		vals.append(filters.get("company"))

	if filters.get("customer"):
		conditions.append("so.customer = %s")
		vals.append(filters.get("customer"))

	if filters.get("customer_group"):
		conditions.append("cust.customer_group = %s")
		vals.append(filters.get("customer_group"))	

	return " AND ".join(conditions), vals

def get_data(filters: dict) -> list[dict]:
	date_cond, date_vals = "", []
	fd, td = filters.get("from_date"), filters.get("to_date")

	if fd and td:
		date_cond = "AND so.transaction_date BETWEEN %s AND %s"
		date_vals.extend([fd, td])

	conditions, vals = get_conditions(filters)

	w_states = ["Proforma Invoice", "Invoiced"]
	wf_cond = "AND so.workflow_state IN ({})".format(", ".join(["%s"] * len(w_states)))

	bind_vals = w_states + date_vals + vals

	sales_orders = frappe.db.sql(f"""
		SELECT
			so.transaction_date AS posting_date,
			'Customer' AS party_type,
			so.customer,
			ps.due_date AS due_date,
			so.name AS sales_order,
			so.rounded_total AS so_rounded_total,
			cust.customer_group,
			MAX(CASE WHEN si.name IS NOT NULL THEN si.name ELSE NULL END) AS sales_invoice,
			MAX(si.rounded_total) AS si_rounded_total,
			MAX((
				SELECT SUM(per.allocated_amount)
				FROM `tabPayment Entry Reference` per
				JOIN `tabPayment Entry` pe ON pe.name = per.parent
				WHERE per.reference_doctype = 'Sales Invoice'
				  AND per.reference_name = si.name
				  AND pe.docstatus = 1
			)) AS paid_amount

		FROM `tabSales Order` so
		LEFT JOIN `tabCustomer` cust ON cust.name = so.customer
		LEFT JOIN `tabPayment Schedule` ps ON ps.parent = so.name
		LEFT JOIN `tabSales Invoice Item` sii ON sii.sales_order = so.name
		LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1

		WHERE so.docstatus = 1
		  {wf_cond}
		  {date_cond}
		  {"AND " + conditions if conditions else ""}
		GROUP BY so.name
	""", bind_vals, as_dict=True)

	result = []
	for row in sales_orders:
		if row.sales_invoice:
			row.voucher_type = "Sales Invoice"
			row.voucher_no = row.sales_invoice
			row.grand_total = row.si_rounded_total or 0
		else:
			row.voucher_type = "Sales Order"
			row.voucher_no = row.sales_order
			row.grand_total = row.so_rounded_total or 0

		row.paid_amount = row.paid_amount or 0
		row.outstanding_amount = row.grand_total - row.paid_amount
		result.append(row)

	return result
