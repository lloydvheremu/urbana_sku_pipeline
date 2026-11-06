from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    hubstaff_user_id = fields.Char(string="Hubstaff User ID", copy=False, index=True, groups="hr.group_hr_user")
