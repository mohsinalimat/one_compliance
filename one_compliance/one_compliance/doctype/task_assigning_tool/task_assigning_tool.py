# # Copyright (c) 2023, efeone and contributors
# # For license information, please see license.txt


import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class TaskAssigningTool(Document):
    pass


@frappe.whitelist()
def get_users_by_department(doctype, txt, searchfield, start, page_len, filters):
    exclude_email = filters.get("exclude_email")
    department = filters.get("department")

    employees = frappe.get_all(
        "Employee",
        filters={"department": department},
        fields=["user_id"],
    )
    user_ids = [emp.user_id for emp in employees if emp.user_id]

    if not user_ids:
        return []

    if exclude_email in user_ids:
        user_ids.remove(exclude_email)

    users = frappe.get_all(
        "User",
        filters={"name": ["in", user_ids], "enabled": 1},
        or_filters=[["name", "like", f"%{txt}%"], ["full_name", "like", f"%{txt}%"]],
        fields=["name", "full_name"],
        start=start,
        page_length=page_len,
    )

    return [(user["name"], user["full_name"]) for user in users]


@frappe.whitelist()
def reassign_tasks(assign_from, assign_to, selected_tasks_json):
    selected_tasks = frappe.parse_json(selected_tasks_json)
    assigned_projects = set()
    projects_to_check = set()

    for task_id in selected_tasks:
        task_doc = frappe.get_doc("Task", task_id)
        frappe.db.set_value("Task", task_id, "assigned_to", assign_to)

        if task_doc.project:
            projects_to_check.add(task_doc.project)

            if task_doc.project not in assigned_projects:
                try:
                    exists = frappe.db.exists("ToDo", {
                        "reference_type": "Project",
                        "reference_name": task_doc.project,
                        "allocated_to": assign_to,
                        "status": "Open"
                    })
                    if not exists:
                        frappe.desk.form.assign_to.add(args={
                            "assign_to": json.dumps([assign_to]),
                            "doctype": "Project",
                            "name": task_doc.project,
                            "description": f"Project assigned due to task reassignment from {assign_from}"
                        })
                    assigned_projects.add(task_doc.project)
                except Exception as e:
                    frappe.log_error(f"Error assigning project {task_doc.project} to user {assign_to}: {str(e)}")

        old_todo_name = frappe.get_value("ToDo", {
            "reference_type": "Task",
            "reference_name": task_id,
            "allocated_to": assign_from,
            "status": ["!=", "Closed"]
        }, "name")

        if old_todo_name:
            frappe.get_doc({
                "doctype": "ToDo",
                "owner": assign_to,
                "allocated_to": assign_to,
                "assigned_by": assign_from,
                "reference_type": "Task",
                "reference_name": task_id,
                "description": f"Task reassigned from {assign_from}",
                "status": "Open",
                "date": now()
            }).insert(ignore_permissions=True)

            old_todo = frappe.get_doc("ToDo", old_todo_name)
            old_todo.status = "Closed"
            old_todo.save(ignore_permissions=True)

    for project in projects_to_check:
        remove_user_from_project_if_no_tasks(project, assign_from)

    frappe.db.commit()
    return "Tasks reassigned successfully"


def remove_user_from_project_if_no_tasks(project_name, user):
    try:
        remaining_tasks = frappe.db.count("Task", {
            "project": project_name,
            "assigned_to": user,
            "status": ["not in", ["Completed", "Cancelled"]]
        })

        if remaining_tasks == 0:
            todo_name = frappe.db.get_value("ToDo", {
                "reference_type": "Project",
                "reference_name": project_name,
                "allocated_to": user,
                "status": "Open"
            }, "name")

            if todo_name:
                todo_doc = frappe.get_doc("ToDo", todo_name)
                todo_doc.status = "Closed"
                todo_doc.save(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Error removing project {project_name} from user {user}: {str(e)}")


@frappe.whitelist()
def get_compliance_categories_for_user(doctype, txt, searchfield, start, page_len, filters):
    user_id = filters.get("user_id")
    employee = frappe.get_doc("Employee", {"user_id": user_id})

    if employee:
        compliance_categories = frappe.get_all(
            "Compliance Category",
            filters={"department": employee.department},
            fields=["name", "department"]
        )
        return [(cat["name"], cat["department"]) for cat in compliance_categories]

    return []


@frappe.whitelist()
def get_compliance_executives(compliance_category):
    return frappe.get_all(
        "Compliance Executive",
        filters={"parent": compliance_category},
        fields=["employee", "designation", "employee_name"]
    )


@frappe.whitelist()
def add_employee_to_compliance_executive(employee, compliance_category):
    try:
        employee_doc = frappe.get_doc("Employee", {"user_id": employee})
        compliance_doc = frappe.get_doc("Compliance Category", compliance_category)

        if employee_doc and compliance_doc:
            for executive in compliance_doc.compliance_executive:
                if executive.employee == employee_doc.name:
                    frappe.msgprint("Employee already exists")
                    return False

            new_exec = frappe.new_doc("Compliance Executive")
            new_exec.employee = employee_doc.name
            new_exec.designation = employee_doc.designation
            new_exec.employee_name = employee_doc.employee_name

            compliance_doc.append("compliance_executive", new_exec)
            compliance_doc.save()
            frappe.db.commit()
            return True

        return False
    except Exception:
        frappe.log_error(frappe.get_traceback(), _("Error in adding employee to Compliance Executive"))
        return False


@frappe.whitelist()
def get_available_subcategories(compliance_category, employee):
    subcategories = frappe.get_all(
        "Compliance Sub Category",
        filters={"compliance_category": compliance_category},
        fields=["name"]
    )

    employee_doc = frappe.get_doc("Employee", {"user_id": employee})

    for subcat in subcategories:
        doc = frappe.get_doc("Compliance Sub Category", subcat["name"])
        subcat["status"] = "added" if any(ex.employee == employee_doc.name for ex in doc.compliance_executive) else "not added"

    return subcategories


@frappe.whitelist()
def add_to_subcategories(employee, compliance_category, selected_subcategories):
    try:
        employee_doc = frappe.get_doc("Employee", {"user_id": employee})
        subcategories = json.loads(selected_subcategories)

        for subcat_name in subcategories:
            subcat_doc = frappe.get_doc("Compliance Sub Category", subcat_name)

            if all(ex.employee != employee_doc.name for ex in subcat_doc.compliance_executive):
                new_exec = frappe.new_doc("Compliance Executive")
                new_exec.employee = employee_doc.name
                new_exec.designation = employee_doc.designation
                new_exec.employee_name = employee_doc.employee_name

                subcat_doc.append("compliance_executive", new_exec)
                subcat_doc.save()

        frappe.db.commit()
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), _("Error in adding employee to Compliance Sub Categories"))
        return False


@frappe.whitelist()
def get_tasks_for_user(assign_from):
    tasks = frappe.db.get_all(
        "Task",
        filters={
            "_assign": ["like", f"%{assign_from}%"],
            "status": ["not in", ["Completed", "Cancelled", "Template"]],
        },
        fields=["name", "subject", "project"]
    )

    return [
        {"task_id": task.name, "subject": task.subject, "project": task.project}
        for task in tasks
    ]
