# Copyright (c) 2023, efeone and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class OutwardRegister(Document):

    def on_submit(self):
        if not self.if_outward_only:
            self.update_inward_child_table()

    def update_inward_child_table(self):
        """ Method to update status of Inward child table based on Outward child table """
        if not self.inward_register:
            return

        inward_doc = frappe.get_doc('Inward Register', self.inward_register)
        for document_types in self.document_register_type:
            document_doc = document_types.document_register_type
            for register_types in inward_doc.register_type_detail:
                if register_types.document_register_type == document_doc:
                    register_types.status = 'Returned'
                    register_types.outward_register = self.name
        inward_doc.save()



@frappe.whitelist()
def disable_add_or_view_digital_signature_button(customer):
	''' Method to check the register type is outward register in the for updated signature table with same customer '''
	if frappe.db.exists('Digital Signature', {'customer' : customer}):
		digital_signature_doc = frappe.get_doc('Digital Signature', {'customer' : customer})
		for digital_signature in digital_signature_doc.digital_signature_details:
			if digital_signature.register_type == 'Outward Register':
				return 1

@frappe.whitelist()
def set_filter_for_document_register_type(doctype, txt, searchfield, start, page_len, filters):
	''' Method to set filter on document register type field to get Issued document registers '''
	if filters:
		query = '''
			SELECT
				rtd.document_register_type
			FROM
				`tabRegister Type Detail` as rtd ,
				`tabInward Register` as ir
			WHERE
				ir.name = rtd.parent AND
				rtd.status = 'Issued' AND
				ir.name = %(inward_register)s
			'''
		values = frappe.db.sql(query.format(**{
			}), {
			'inward_register': filters['inward_register'],
		})
		return values
