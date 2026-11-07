from odoo import _, api, fields, models


class UrbanaHandoverWizard(models.TransientModel):
    _name = "urbana.handover.wizard"
    _description = "Hand Over a SKU"

    project_id = fields.Many2one("project.project", required=True, readonly=True)
    notes = fields.Text(help="Anything the next person needs to know.")

    def action_confirm(self):
        self.ensure_one()
        self.project_id.action_advance(notes=self.notes)
        return {"type": "ir.actions.act_window_close"}


class UrbanaSendBackWizard(models.TransientModel):
    _name = "urbana.send.back.wizard"
    _description = "Send a SKU Back"

    project_id = fields.Many2one("project.project", required=True, readonly=True)
    allowed_stage_ids = fields.Many2many(
        "urbana.pipeline.stage", compute="_compute_allowed_stage_ids"
    )
    target_stage_id = fields.Many2one(
        "urbana.pipeline.stage",
        string="Send Back To",
        required=True,
        domain="[('id', 'in', allowed_stage_ids)]",
    )
    reason = fields.Text(required=True)

    @api.depends("project_id.pipeline_stage_id")
    def _compute_allowed_stage_ids(self):
        for wizard in self:
            stages = wizard.project_id._pipeline_stages()
            current = wizard.project_id.pipeline_stage_id
            earlier = stages[: stages.ids.index(current.id)] if current in stages else stages.browse()
            wizard.allowed_stage_ids = earlier.filtered("is_return_target")

    def action_confirm(self):
        self.ensure_one()
        self.project_id.action_send_back(self.target_stage_id, self.reason)
        return {"type": "ir.actions.act_window_close"}


class UrbanaRequestChangesWizard(models.TransientModel):
    _name = "urbana.request.changes.wizard"
    _description = "Request Changes on a Stage"

    task_id = fields.Many2one("project.task", required=True, readonly=True)
    allowed_stage_ids = fields.Many2many(
        "urbana.pipeline.stage", compute="_compute_allowed_stage_ids"
    )
    target_stage_id = fields.Many2one(
        "urbana.pipeline.stage",
        string="Send Back To",
        compute="_compute_target_stage_id",
        store=True,
        readonly=False,
        domain="[('id', 'in', allowed_stage_ids)]",
        help="Defaults to the previous stage. Empty on the first stage.",
    )
    reason = fields.Text(required=True)
    update_id = fields.Many2one("project.update", readonly=True)

    @api.depends("task_id.project_id.pipeline_stage_id")
    def _compute_allowed_stage_ids(self):
        for wizard in self:
            project = wizard.task_id.project_id
            stages = project._pipeline_stages()
            current = project.pipeline_stage_id
            earlier = stages[: stages.ids.index(current.id)] if current in stages else stages.browse()
            wizard.allowed_stage_ids = earlier.filtered("is_return_target")

    @api.depends("allowed_stage_ids")
    def _compute_target_stage_id(self):
        for wizard in self:
            stages = wizard.task_id.project_id._pipeline_stages()
            current = wizard.task_id.project_id.pipeline_stage_id
            index = stages.ids.index(current.id) if current in stages else 0
            previous = stages[index - 1] if index else stages.browse()
            wizard.target_stage_id = previous if previous in wizard.allowed_stage_ids else False

    def action_confirm(self):
        self.ensure_one()
        self.update_id = self.task_id._request_changes(self.reason, self.target_stage_id)
        # Reopen this wizard so the "View Update" button can be shown.
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_view_update(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Project Update"),
            "res_model": "project.update",
            "res_id": self.update_id.id,
            "view_mode": "form",
            "target": "current",
        }
