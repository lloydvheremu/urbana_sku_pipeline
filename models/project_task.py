from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .project_project import INTERNAL, MANAGER_GROUP, REVIEWER_GROUP

PROTECTED_FIELDS = {"pipeline_stage_id", "is_approved", "approved_by", "approved_date"}
# A stage task only gets these states from the pipeline buttons.
LOCKED_STATES = {"1_done", "03_approved", "02_changes_requested"}


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
    is_current_stage = fields.Boolean(compute="_compute_is_current_stage")
    project_is_last_stage = fields.Boolean(related="project_id.is_last_stage")

    @api.depends("pipeline_stage_id", "project_id.pipeline_stage_id")
    def _compute_is_current_stage(self):
        for task in self:
            task.is_current_stage = bool(
                task.pipeline_stage_id and task.project_id.pipeline_stage_id == task.pipeline_stage_id
            )

    @api.depends("pipeline_stage_id", "is_approved", "project_id.pipeline_stage_id")
    def _compute_can_review(self):
        for task in self:
            stage = task.pipeline_stage_id
            task.can_review = bool(
                stage.requires_approval
                and not task.is_approved
                and task.project_id.pipeline_stage_id == stage
            )

    def action_open_handover_wizard(self):
        self.ensure_one()
        return self.project_id.action_open_handover_wizard()

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
        if (
            vals.get("state") in LOCKED_STATES
            and not self.env.su
            and not self.env.context.get(INTERNAL)
            and self.filtered("pipeline_stage_id")
        ):
            raise UserError(
                _("A stage task is marked done, approved or sent back with the pipeline buttons.")
            )
        return super().write(vals)

    def unlink(self):
        if (
            not self.env.su
            and not self.env.context.get(INTERNAL)
            and self.filtered("pipeline_stage_id")
        ):
            raise UserError(
                _("A stage task cannot be deleted. It goes away when its SKU is deleted.")
            )
        return super().unlink()

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
        """Send Back: ask for the reason (and the stage, defaulting to the previous one)."""
        self.ensure_one()
        self._check_reviewer()
        return {
            "type": "ir.actions.act_window",
            "name": _("Request Changes"),
            "res_model": "urbana.request.changes.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_task_id": self.id},
        }

    def _request_changes(self, reason, target=None):
        """Reject this stage's work. Later stages: a send back through
        action_send_back, to `target` or by default the previous stage. First stage: nothing earlier exists, so only this task
        is reopened and an at-risk update is logged. Returns that project.update."""
        self.ensure_one()
        self._check_reviewer()
        project = self.project_id
        if not self.pipeline_stage_id or project.pipeline_stage_id != self.pipeline_stage_id:
            raise UserError(_("Only the stage the SKU is currently in can be reviewed."))
        reason = (reason or "").strip()
        if not reason:
            raise UserError(_("A reason is required to request changes."))
        stages = project._pipeline_stages()
        if self.pipeline_stage_id == stages[:1]:
            self.with_context(**{INTERNAL: True}).write({
                "is_approved": False,
                "approved_by": False,
                "approved_date": False,
                "state": "02_changes_requested",
            })
            self.message_post(body=_("Changes requested."))
            return project._post_update(
                _("%(sku)s: changes requested on %(stage)s", sku=project._label(),
                  stage=self.pipeline_stage_id.name),
                "at_risk",
                Markup("<p>{}</p><p><b>{}</b> {}</p>").format(
                    _("%(who)s requested changes on %(stage)s.",
                      who=self.env.user.name, stage=self.pipeline_stage_id.name),
                    _("Reason:"), reason,
                ),
            )
        previous = target or stages[stages.ids.index(self.pipeline_stage_id.id) - 1]
        project.action_send_back(previous, reason)
        update = self.env["urbana.sku.handover"].sudo().search(
            [("project_id", "=", project.id)], order="id desc", limit=1
        ).update_id
        # Also raise an activity on the SKU itself, for the previous stage's
        # assignees, or the project manager when nobody is assigned.
        assignees = project._task_for(previous).user_ids or project.user_id
        # Reviewers may not write projects; the activity is created privileged.
        for user in assignees:
            project.sudo().activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Changes requested on %(stage)s", stage=self.pipeline_stage_id.name),
                note=reason,
                user_id=user.id,
            )
        return update
