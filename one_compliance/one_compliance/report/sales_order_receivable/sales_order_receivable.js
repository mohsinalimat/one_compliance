// Copyright (c) 2025, efeone and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Order Receivable"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "report_date",
            label: __("Order Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer",
        },
        {
            fieldname: "customer_group",
            label: __("Customer Group"),
            fieldtype: "Link",
            options: "Customer Group",
        },
        {
            fieldname: "sales_person",
            label: __("Sales Person"),
            fieldtype: "Link",
            options: "Sales Person",
        },
        {
            fieldname: "territory",
            label: __("Territory"),
            fieldtype: "Link",
            options: "Territory",
        },
        {
            fieldname: "group_by_customer",
            label: __("Group By Customer"),
            fieldtype: "Check",
        },
        {
            fieldname: "show_sales_person",
            label: __("Show Sales Person"),
            fieldtype: "Check",
        },
        {
            fieldname: "ageing_based_on",
            label: __("Ageing Based On"),
            fieldtype: "Select",
            options: "Due Date\nPosting Date",
            default: "Due Date",
        },
        {
            fieldname: "range",
            label: __("Ageing Range"),
            fieldtype: "Data",
            default: "30, 60, 90, 120",
        },
        {
            fieldname: "include_invoiced",
            label: __("Include Invoiced"),
            fieldtype: "Check",
        },
        {
            fieldname: "include_paid",
            label: __("Include Paid"),
            fieldtype: "Check",
        }
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (data && data.bold) {
            value = `<b>${value}</b>`;
        }
        return value;
    }
};
