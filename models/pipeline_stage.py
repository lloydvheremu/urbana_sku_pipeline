from odoo import fields, models


class UrbanaPipelineStage(models.Model):
    _name = "urbana.pipeline.stage"
    _description = "SKU Pipeline Stage"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    job_id = fields.Many2one(
        "hr.job",
        string="Required Job Position",
        help="Only employees with this job position can be assigned to the "
        "task of this stage. Leave empty to allow anyone.",
    )
    min_hours = fields.Float(
        string="Minimum Hours",
        help="Hours that must be logged on the stage task before the SKU can "
        "leave this stage.",
    )
    requires_approval = fields.Boolean(
        help="A reviewer must approve the stage task before the SKU can leave "
        "this stage, and before it can reach any later stage.",
    )
    export_ready = fields.Boolean(
        string="Ready for Export",
        help="SKUs in this stage count as ready for export.",
    )
    is_return_target = fields.Boolean(
        string="Can Be Sent Back To",
        default=True,
        help="Allow a reviewer to send a SKU back to this stage.",
    )

    _name_uniq = models.Constraint("UNIQUE(name)", "Stage names must be unique.")
    _min_hours_positive = models.Constraint(
        "CHECK(min_hours >= 0)", "Minimum hours cannot be negative."
    )
