from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class UrbanaSkuImage(models.Model):
    """A picture kept with a SKU, usually a screenshot of the work done on a stage."""

    _name = "urbana.sku.image"
    _description = "SKU Image"
    _order = "id desc"

    name = fields.Char(string="Caption")
    image = fields.Image(required=True, max_width=1920, max_height=1920)
    project_id = fields.Many2one("project.project", string="SKU", required=True, ondelete="cascade", index=True)
    task_id = fields.Many2one(
        "project.task",
        string="Stage Task",
        ondelete="cascade",
        index=True,
        domain="[('project_id', '=', project_id)]",
        help="The stage task this picture belongs to. Defaults to the SKU's current stage.",
    )
    stage_id = fields.Many2one(related="task_id.pipeline_stage_id", string="Stage")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("task_id") and not vals.get("project_id"):
                vals["project_id"] = self.env["project.task"].browse(vals["task_id"]).project_id.id
            elif vals.get("project_id") and not vals.get("task_id"):
                project = self.env["project.project"].browse(vals["project_id"])
                if project.is_sku and project.pipeline_stage_id:
                    task = project._task_for(project.pipeline_stage_id)
                    if task:
                        vals["task_id"] = task.id
        return super().create(vals_list)

    @api.constrains("project_id", "task_id")
    def _check_task_belongs_to_sku(self):
        for image in self:
            if image.task_id and image.task_id.project_id != image.project_id:
                raise ValidationError(_("The task must belong to the same SKU as the image."))
