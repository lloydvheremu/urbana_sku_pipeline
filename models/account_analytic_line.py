from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    hubstaff_entry_id = fields.Char(string="Hubstaff Entry ID", copy=False, index=True)
    source = fields.Selection(
        [("manual", "Manual"), ("hubstaff", "Hubstaff")],
        default="manual",
        required=True,
        copy=False,
    )

    _hubstaff_entry_uniq = models.Constraint(
        "UNIQUE(hubstaff_entry_id)",
        "This Hubstaff time entry has already been imported.",
    )
