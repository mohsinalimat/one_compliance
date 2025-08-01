# Copyright (c) 2023, efeone and contributors
# For license information, please see license.txt

import json
from typing import List, Set, Tuple, Optional

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class TaskAssigningTool(Document):
    pass


@frappe.whitelist()
def get_users_by_department(doctype, txt, searchfield, start, page_len, filters):
    """Get users filtered by department with search functionality."""
    exclude_email = filters.get("exclude_email")
    department = filters.get("department")

    if not department:
        return []

    # Get user IDs from employees in the department
    user_ids = frappe.db.get_list(
        "Employee",
        filters={"department": department},
        fields=["user_id"],
        pluck="user_id"
    )

    # Filter out None values and excluded email
    user_ids = [uid for uid in user_ids if uid and uid != exclude_email]

    if not user_ids:
        return []

    search_filters = {"name": ["in", user_ids], "enabled": 1}
    or_filters = []
    if txt:
        or_filters = [
            ["name", "like", f"%{txt}%"],
            ["full_name", "like", f"%{txt}%"]
        ]

    users = frappe.get_all(
        "User",
        filters=search_filters,
        or_filters=or_filters or None,
        fields=["name", "full_name"],
        start=start,
        page_length=page_len,
    )

    return [(user["name"], user["full_name"]) for user in users]


@frappe.whitelist()
def reassign_tasks(assign_from: str, assign_to: str, selected_tasks_json: str) -> str:
    """Reassign tasks from one user to another and handle project assignments."""
    selected_tasks = frappe.parse_json(selected_tasks_json)

    if not selected_tasks:
        return "No tasks selected for reassignment"

    assigned_projects: Set[str] = set()
    projects_to_check: Set[str] = set()

    # Process all tasks
    for task_id in selected_tasks:
        task_doc = frappe.get_doc('Task', task_id)

        # Update task assignment
        frappe.db.set_value('Task', task_id, 'assigned_to', assign_to)
        
        # Handle project assignment if task has a project
        if task_doc.project:
            projects_to_check.add(task_doc.project)
            _assign_project_if_needed(task_doc.project, assign_to, assign_from, assigned_projects)

        # Handle ToDo reassignment
        _reassign_todo_item(task_id, assign_from, assign_to)

    # Clean up project assignments for users with no remaining tasks
    for project_name in projects_to_check:
        _remove_user_from_project_if_no_tasks(project_name, assign_from)

    frappe.db.commit()
    return "Tasks reassigned successfully"


def _assign_project_if_needed(project_name: str, assign_to: str, assign_from: str, assigned_projects: Set[str]) -> None:
    """Assign project to user if not already assigned."""
    if project_name in assigned_projects:
        return

    try:
        # Check if project is already assigned to the user
        existing_assignment = frappe.db.exists('ToDo', {
            'reference_type': 'Project',
            'reference_name': project_name,
            'allocated_to': assign_to,
            'status': 'Open'
        })

        if not existing_assignment:
            frappe.desk.form.assign_to.add(args={
                'assign_to': json.dumps([assign_to]),
                'doctype': 'Project',
                'name': project_name,
                'description': f'Project assigned due to task reassignment from {assign_from}'
            })

        assigned_projects.add(project_name)

    except Exception as e:
        frappe.log_error(f"Error assigning project {project_name} to user {assign_to}: {str(e)}")


def _reassign_todo_item(task_id: str, assign_from: str, assign_to: str) -> None:
    """Reassign ToDo item for a task."""
    # Find existing ToDo for the task
    old_todo_name = frappe.db.get_value('ToDo', {
        'reference_name': task_id,
        'reference_type': 'Task',
        'status': ['!=', 'Closed'],
        'allocated_to': assign_from
    }, 'name')

    if old_todo_name:
        # Create new ToDo for the assignee
        frappe.get_doc({
            'doctype': 'ToDo',
            'owner': assign_to,
            'allocated_to': assign_to,
            'assigned_by': assign_from,
            'reference_type': 'Task',
            'reference_name': task_id,
            'description': f"Task reassigned from {assign_from}",
            'status': 'Open',
            'date': now()
        }).insert(ignore_permissions=True)

        # Close old ToDo
        frappe.db.set_value('ToDo', old_todo_name, 'status', 'Closed')


def _remove_user_from_project_if_no_tasks(project_name: str, user: str) -> None:
    """Remove user from project assignment if they have no remaining open tasks."""
    try:
        # Check remaining open tasks for user in project
        remaining_tasks = frappe.db.count('Task', {
            'project': project_name,
            'assigned_to': user,
            'status': ['not in', ['Completed', 'Cancelled']]
        })
        
        if remaining_tasks == 0:
            # Close project assignment if exists
            project_todo_name = frappe.db.get_value('ToDo', {
                'reference_type': 'Project',
                'reference_name': project_name,
                'allocated_to': user,
                'status': 'Open'
            }, 'name')
            
            if project_todo_name:
                frappe.db.set_value('ToDo', project_todo_name, 'status', 'Closed')
                
    except Exception as e:
        frappe.log_error(f"Error removing project {project_name} from user {user}: {str(e)}")


# Remove the duplicate function definition
remove_user_from_project_if_no_tasks = _remove_user_from_project_if_no_tasks


@frappe.whitelist()
def get_compliance_categories_for_user(doctype, txt, searchfield, start, page_len, filters):
    """Get compliance categories for a user based on their department."""
    user_id = filters.get("user_id")

    if not user_id:
        return []

    # Get employee department efficiently
    department = frappe.db.get_value("Employee", {"user_id": user_id}, "department")

    if not department:
        return []

    # Get compliance categories for the department
    compliance_categories = frappe.get_all(
        "Compliance Category",
        filters={"department": department},
        fields=["name", "department"],
    )

    return [(category["name"], category["department"]) for category in compliance_categories]


@frappe.whitelist()
def get_compliance_executives(compliance_category: str) -> List[dict]:
    """Get compliance executives for a specific category."""
    return frappe.get_all(
        "Compliance Executive",
        filters={"parent": compliance_category},
        fields=["employee", "designation", "employee_name"],
    )


@frappe.whitelist()
def add_employee_to_compliance_executive(employee: str, compliance_category: str) -> bool:
    """Add an employee to compliance executive table."""
    try:
        # Get employee and compliance category documents
        employee_doc = frappe.get_doc("Employee", {"user_id": employee})
        compliance_category_doc = frappe.get_doc("Compliance Category", compliance_category)

        # Check if employee already exists in the table
        existing_employee_names = {exec.employee for exec in compliance_category_doc.compliance_executive}

        if employee_doc.name in existing_employee_names:
            frappe.msgprint("Employee is already existing")
            return False

        # Add new executive
        executive = frappe.new_doc("Compliance Executive")
        executive.employee = employee_doc.name
        executive.designation = employee_doc.designation
        executive.employee_name = employee_doc.employee_name

        compliance_category_doc.append("compliance_executive", executive)
        compliance_category_doc.save()
        frappe.db.commit()

        return True

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            _("Error in adding employee to Compliance Executive"),
        )
        return False


@frappe.whitelist()
def get_available_subcategories(compliance_category: str, employee: str) -> List[dict]:
    """Get available subcategories with their assignment status for an employee."""
    # Get all subcategories for the category
    subcategories = frappe.get_all(
        "Compliance Sub Category",
        filters={"compliance_category": compliance_category},
        fields=["name"],
    )

    if not subcategories:
        return []

    # Get employee document once
    employee_doc = frappe.get_doc("Employee", {"user_id": employee})

    # Get all compliance executives for these subcategories in one query
    subcategory_names = [sub["name"] for sub in subcategories]
    executives = frappe.get_all(
        "Compliance Executive",
        filters={"parent": ["in", subcategory_names], "employee": employee_doc.name},
        fields=["parent"],
        pluck="parent"
    )

    assigned_subcategories = set(executives)

    # Add status to each subcategory
    for subcategory in subcategories:
        subcategory["status"] = "added" if subcategory["name"] in assigned_subcategories else "not added"

    return subcategories


@frappe.whitelist()
def add_to_subcategories(employee: str, compliance_category: str, selected_subcategories: str) -> bool:
    """Add employee to selected subcategories."""
    try:
        # Parse and validate inputs
        employee_doc = frappe.get_doc("Employee", {"user_id": employee})
        compliance_subcategories = json.loads(selected_subcategories)

        if not compliance_subcategories:
            return False

        # Get existing assignments to avoid duplicates
        existing_assignments = frappe.get_all(
            "Compliance Executive",
            filters={
                "parent": ["in", compliance_subcategories],
                "employee": employee_doc.name
            },
            fields=["parent"],
            pluck="parent"
        )

        existing_set = set(existing_assignments)

        # Process each subcategory
        for subcategory_name in compliance_subcategories:
            if subcategory_name in existing_set:
                continue

            compliance_subcategory_doc = frappe.get_doc("Compliance Sub Category", subcategory_name)

            # Create and append new executive
            executive = frappe.new_doc("Compliance Executive")
            executive.employee = employee_doc.name
            executive.designation = employee_doc.designation
            executive.employee_name = employee_doc.employee_name

            compliance_subcategory_doc.append("compliance_executive", executive)
            compliance_subcategory_doc.save()

        frappe.db.commit()
        return True

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            _("Error in adding employee to Compliance Sub Categories"),
        )
        return False


@frappe.whitelist()
def get_tasks_for_user(assign_from: str) -> List[dict]:
    """Fetch tasks for a specific user."""

    return frappe.db.get_all(
        "Task",
        filters={
            "_assign": ["like", f"%{assign_from}%"],
            "status": ["not in", ["Completed", "Cancelled", "Template"]],
        },
        fields=["name as task_id", "subject", "project"],
    )