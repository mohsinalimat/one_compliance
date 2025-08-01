# Copyright (c) 2023, efeone and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now
from one_compliance.one_compliance.utils import add_custom


class TaskAssigningTool(Document):
    pass


@frappe.whitelist()
def get_users_by_department(doctype, txt, searchfield, start, page_len, filters):

    exclude_email = filters.get("exclude_email")
    # Query the Employee doctype to filter users by department
    user_ids = frappe.get_all(
        "Employee",
        filters={"department": filters.get("department")},
        pluck="user_id"
    )

    # Filter out None and the excluded email
    user_ids = [uid for uid in user_ids if uid and uid != exclude_email]

    if not user_ids:
        return []

    #  Add search filter using 'txt'
    users = frappe.get_all(
        "User",
        filters={"name": ["in", user_ids], "enabled": 1},
        or_filters=[["name", "like", f"%{txt}%"], ["full_name", "like", f"%{txt}%"]],
        fields=["name", "full_name"],
        start=start,
        page_length=page_len,
    )

    # Build result list
    return [(user["name"], user["full_name"]) for user in users]


@frappe.whitelist()
def reassign_tasks(assign_from, assign_to, selected_tasks_json):
    
    selected_tasks = frappe.parse_json(selected_tasks_json)

    assigned_projects = set()  
    projects_to_check = set()

    for task_id in selected_tasks:

        task_doc = frappe.get_doc('Task', task_id)

        frappe.db.set_value('Task', task_id, 'assigned_to', assign_to)
        
        if task_doc.project:
            projects_to_check.add(task_doc.project)
            
            if task_doc.project not in assigned_projects:
                try:
                    existing_assignment = frappe.db.exists('ToDo', {
                        'reference_type': 'Project',
                        'reference_name': task_doc.project,
                        'allocated_to': assign_to,
                        'status': 'Open'
                    })
                    
                    if not existing_assignment:
                        frappe.desk.form.assign_to.add(args={
                            'assign_to': json.dumps([assign_to]),
                            'doctype': 'Project',
                            'name': task_doc.project,
                            'description': f'Project assigned due to task reassignment from {assign_from}'
                        })
                        
                    assigned_projects.add(task_doc.project)
                    
                except Exception as e:
                    frappe.log_error(f"Error assigning project {task_doc.project} to user {assign_to}: {str(e)}")

        # Get the reference name of the 'ToDo' document associated with the selected task
        old_todo_reference = frappe.get_value('ToDo', {
            'reference_name': task_id, 
            'reference_type': 'Task', 
            'status': ['!=', 'Closed'], 
            'allocated_to': assign_from
        }, 'name')

        if old_todo_reference:
            add_custom({
                'assign_to': json.dumps([assign_to]),
                'doctype': 'Task',
                'name': task_id,
                'description': f"Task reassigned from {assign_from}",
                'assigned_by': assign_from
            })

            frappe.db.set_value('ToDo', old_todo_reference, 'status', 'Closed', update_modified=False)


    for project_name in projects_to_check:
        remove_user_from_project_if_no_tasks(project_name, assign_from)

    frappe.db.commit()
    return "Tasks reassigned successfully"

def remove_user_from_project_if_no_tasks(project_name, user):
    """
    Remove user from project assignment if they have no remaining open tasks in the project
    """
    try:
        # Check if user has any remaining open tasks in this project
        remaining_tasks = frappe.db.count('Task', {
            'project': project_name,
            'assigned_to': user,
            'status': ['not in', ['Completed', 'Cancelled']]
        })
        
        if remaining_tasks == 0:
            # Check if user has project assignment
            project_todo = frappe.db.get_value('ToDo', {
                'reference_type': 'Project',
                'reference_name': project_name,
                'allocated_to': user,
                'status': 'Open'
            }, 'name')
            
            if project_todo:
                frappe.db.set_value('ToDo', project_todo, 'status', 'Closed', update_modified=False)
                
            
    except Exception as e:
        frappe.log_error(f"Error removing project {project_name} from user {user}: {str(e)}")


@frappe.whitelist()
def get_compliance_categories_for_user(
    doctype, txt, searchfield, start, page_len, filters
):
    user_id = filters.get("user_id")

    # Find the Employee based on the user_id
    employee = frappe.get_doc("Employee", {"user_id": user_id})

    if employee:
        # Get the department of the employee
        department = employee.department

        # Query the Compliance Category DocType
        compliance_categories = frappe.get_all(
            "Compliance Category",
            filters={"department": department},
            fields=["name", "department"],
        )

        category_names = []  # Initialize an empty list to store user information

        for category in compliance_categories:
            name = category["name"]
            department = category["department"]

            category_names.append(
                (name, department)
            )  # Add email and full name as a tuple to the list

        return category_names  # Return the list of email IDs and full names as tuples
    return []


@frappe.whitelist()
def get_compliance_executives(compliance_category):
    child_table_data = frappe.get_all(
        "Compliance Executive",
        filters={"parent": compliance_category},
        fields=["employee", "designation", "employee_name"],
    )
    return child_table_data


@frappe.whitelist()
def add_employee_to_compliance_executive(employee, compliance_category):
    try:
        # Check if the employee and compliance category exist
        employee_doc = frappe.get_doc("Employee", {"user_id": employee})
        compliance_category_doc = frappe.get_doc(
            "Compliance Category", compliance_category
        )

        if employee_doc and compliance_category_doc:
            # Check if the employee is already in the Compliance Executive table for the category
            existing_executive = None
            for executive in compliance_category_doc.compliance_executive:
                if executive.employee == employee_doc.name:
                    existing_executive = executive
                    break

            if not existing_executive:
                # Create a new "Compliance Executive" document and set its fields
                executive = frappe.new_doc("Compliance Executive")
                executive.employee = employee_doc.name
                executive.designation = employee_doc.designation
                executive.employee_name = employee_doc.employee_name

                # Append the new executive to the Compliance Executive table
                compliance_category_doc.append("compliance_executive", executive)

                # Save the Compliance Category document with the updated table
                compliance_category_doc.save()

                frappe.db.commit()
                return True
            else:
                frappe.msgprint("Employee is already existing")
                return False  # Employee is already in the table
        else:
            return False  # Employee or Compliance Category does not exist
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            _("Error in adding employee to Compliance Executive"),
        )
        return False


@frappe.whitelist()
def get_available_subcategories(compliance_category, employee):
    # Query the database to retrieve subcategories related to the selected category
    subcategories = frappe.get_all(
        "Compliance Sub Category",
        filters={"compliance_category": compliance_category},
        fields=["name"],
    )

    # Check if the employee exists in the compliance executive of each subcategory
    employee_doc = frappe.get_doc("Employee", {"user_id": employee})
    for subcategory in subcategories:
        compliance_subcategory_doc = frappe.get_doc(
            "Compliance Sub Category", subcategory["name"]
        )

        is_added = False
        for executive in compliance_subcategory_doc.compliance_executive:
            if executive.employee == employee_doc.name:
                is_added = True
                break

        subcategory["status"] = "added" if is_added else "not added"

    return subcategories


@frappe.whitelist()
def add_to_subcategories(employee, compliance_category, selected_subcategories):

    try:
        # Check if the employee and compliance category exist
        employee_doc = frappe.get_doc("Employee", {"user_id": employee})
        compliance_category_doc = frappe.get_doc(
            "Compliance Category", compliance_category
        )
        compliance_subcategories = json.loads(selected_subcategories)

        if employee_doc and compliance_category_doc:
            for subcategory in compliance_subcategories:

                compliance_subcategory_doc = frappe.get_doc(
                    "Compliance Sub Category", {"name": subcategory}
                )

                if compliance_subcategory_doc:

                    existing_executive = None
                    for executive in compliance_subcategory_doc.compliance_executive:
                        if executive.employee == employee_doc.name:
                            existing_executive = executive
                            break

                    if not existing_executive:
                        # Create a new "Compliance Executive" document and set its fields
                        executive = frappe.new_doc("Compliance Executive")
                        executive.employee = employee_doc.name
                        executive.designation = employee_doc.designation
                        executive.employee_name = employee_doc.employee_name

                        # Append the new executive to the Compliance Executive table
                        compliance_subcategory_doc.append(
                            "compliance_executive", executive
                        )

                        # Save the Compliance Sub Category document with the updated table
                        compliance_subcategory_doc.save()

            frappe.db.commit()
            return True
        else:
            return False
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            _("Error in adding employee to Compliance Sub Categories"),
        )
        return False


@frappe.whitelist()
def get_tasks_for_user(assign_from):
    """
    fetch tasks for this user
    """

    task_details = frappe.db.get_all(
        "Task",
        filters={
            "_assign": ["like", f"%{assign_from}%"],
            "status": ["not in", ["Completed", "Cancelled", "Template"]],
        },
        fields=["name as task_id", "subject", "project"],
    )

    return task_details