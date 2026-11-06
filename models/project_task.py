from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .project_project import INTERNAL, MANAGER_GROUP, REVIEWER_GROUP

PROTECTED_FIELDS = {"pipeline_stage_id", "is_approved", "approved_by", "approved_date"}


class ProjectTask(models.Model):
    _inherit = "project.task"

    pipeline_stage_id = fields.Many2one(
        "urbana.pipeline.stage",
        string="Pipeline Stage",
        copy=False,
        readonly=True,
        index=True,
        ondelete="restrict",
    )
    is_approved = fields.Boolean(string="Approved", copy=False, readonly=True)
    approved_by = fields.Many2one("res.users", copy=False, readonly=True)
    approved_date = fields.Datetime(copy=False, readonly=True)
    output_url = fields.Char(string="Output Link", help="Link to what this stage produced.")
    hubstaff_task_id = fields.Char(string="Hubstaff Task ID", copy=False, index=True)
    can_review = fields.Boolean(compute="_compute_can_review")

    @api.depends("pipeline_stage_id", "is_approved", "project_id.pipeline_stage_id")
    def _compute_can_review(self):
        for task in self:
            stage = task.pipeline_stage_id
            task.can_review = bool(
                stage.requires_approval
                and not task.is_approved
                and task.project_id.pipeline_stage_id == stage
            )

    @api.constrains("user_ids", "pipeline_stage_id")
    def _check_assignee_job(self):
        for task in self.filtered("pipeline_stage_id"):
            job = task.pipeline_stage_id.job_id
            if not job:
                continue
            for user in task.user_ids:
                if user.sudo().employee_id.job_id != job:
                    raise ValidationError(
                        _(
                            "%(user)s cannot work on %(stage)s: the job position must be %(job)s.",
                            user=user.name,
                            stage=task.pipeline_stage_id.name,
                            job=job.name,
                        )
                    )

    def write(self, vals):
        if (
            PROTECTED_FIELDS & set(vals)
            and not self.env.su
            and not self.env.context.get(INTERNAL)
        ):
            raise UserError(
                _("Stage and approval fields can only be changed with the pipeline buttons.")
            )
        return super().write(vals)

    def _check_reviewer(self):
        user = self.env.user
        if not (self.env.su or user.has_group(REVIEWER_GROUP) or user.has_group(MANAGER_GROUP)):
            raise AccessError(_("Only reviewers can approve or request changes."))

    def action_approve(self):
        self._check_reviewer()
        for task in self:
            stage = task.pipeline_stage_id
            if not stage.requires_approval:
                raise UserError(_("%(stage)s does not need approval.", stage=stage.name))
            if task.project_id.pipeline_stage_id != stage:
                raise UserError(_("Only the stage the SKU is currently in can be approved."))
            if task.is_approved:
                continue
            task.with_context(**{INTERNAL: True}).write({
                "is_approved": True,
                "approved_by": self.env.user.id,
                "approved_date": fields.Datetime.now(),
                "state": "03_approved",
            })
            task.message_post(body=_("%(stage)s approved.", stage=stage.name))
        return True

    def action_request_changes(self):
        self._check_reviewer()
        for task in self:
            if task.project_id.pipeline_stage_id != task.pipeline_stage_id:
                raise UserError(_("Only the stage the SKU is currently in can be reviewed."))
            task.with_context(**{INTERNAL: True}).write({
                "is_approved": False,
                "approved_by": False,
                "approved_date": False,
                "state": "02_changes_requested",
            })
            task.message_post(body=_("Changes requested."))
        return True
