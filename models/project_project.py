from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

INTERNAL = "urbana_pipeline_internal"
REVIEWER_GROUP = "urbana_sku_pipeline.group_urbana_reviewer"
MANAGER_GROUP = "project.group_project_manager"
DONE = "1_done"


class ProjectProject(models.Model):
    _inherit = "project.project"

    is_sku = fields.Boolean(string="Is SKU", copy=False, index=True)
    sku_code = fields.Char(string="SKU Code", copy=False, index=True, tracking=True)
    product_range = fields.Char(string="Product Range")
    pipeline_stage_id = fields.Many2one(
        "urbana.pipeline.stage",
        string="Pipeline Stage",
        copy=False,
        readonly=True,
        tracking=True,
        index=True,
        ondelete="restrict",
    )
    cleanup_state = fields.Selection(
        [
            ("not_started", "Not Started"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
        ],
        string="Cleanup",
        default="not_started",
        copy=False,
        tracking=True,
    )
    export_ready = fields.Boolean(
        related="pipeline_stage_id.export_ready",
        string="Ready for Export",
        store=True,
    )
    awaiting_approval = fields.Boolean(
        compute="_compute_awaiting_approval", store=True
    )
    is_last_stage = fields.Boolean(compute="_compute_stage_flags")
    is_first_stage = fields.Boolean(compute="_compute_stage_flags")
    is_completed = fields.Boolean(compute="_compute_stage_flags")
    handover_ids = fields.One2many("urbana.sku.handover", "project_id")
    hubstaff_project_id = fields.Char(string="Hubstaff Project ID", copy=False, index=True)

    _sku_code_uniq = models.Constraint(
        "UNIQUE(sku_code)", "The SKU code must be unique."
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pipeline_stages(self):
        return self.env["urbana.pipeline.stage"].search([])

    def _task_for(self, stage):
        """The stage task of this SKU. Uses `tasks`, because `task_ids`
        hides closed tasks."""
        return self.tasks.filtered(lambda t: t.pipeline_stage_id == stage)[:1]

    def _label(self):
        return self.sku_code or self.name

    @api.depends("pipeline_stage_id", "pipeline_stage_id.requires_approval",
                 "tasks.is_approved", "tasks.pipeline_stage_id")
    def _compute_awaiting_approval(self):
        for project in self:
            stage = project.pipeline_stage_id
            task = project._task_for(stage) if stage else self.env["project.task"]
            project.awaiting_approval = bool(
                project.is_sku and stage.requires_approval and task and not task.is_approved
            )

    @api.depends("pipeline_stage_id", "tasks.state")
    def _compute_stage_flags(self):
        for project in self:
            stages = project._pipeline_stages()
            stage = project.pipeline_stage_id
            project.is_first_stage = bool(stages and stage == stages[:1])
            project.is_last_stage = bool(stages and stage == stages[-1:])
            last_task = project._task_for(stages[-1:]) if stages else False
            project.is_completed = bool(
                project.is_last_stage and last_task and last_task.state == DONE
            )

    def _stage_blocker(self, stage, task):
        """Return a message if the task stops the SKU leaving the stage."""
        if not task:
            return _("There is no task for the stage %(stage)s.", stage=stage.name)
        if stage.requires_approval and not task.is_approved:
            return _("%(stage)s must be approved before the SKU can move on.", stage=stage.name)
        if float_compare(task.effective_hours, stage.min_hours, precision_digits=2) < 0:
            return _(
                "%(stage)s needs at least %(minimum)s hours logged, %(done)s so far.",
                stage=stage.name,
                minimum=stage.min_hours,
                done=task.effective_hours,
            )
        return False

    def _check_can_move(self, task):
        user = self.env.user
        if (
            self.env.su
            or user in task.user_ids
            or user.has_group(REVIEWER_GROUP)
            or user.has_group(MANAGER_GROUP)
        ):
            return
        raise AccessError(
            _("Only the assignee of this stage, a reviewer or a project manager can do this.")
        )

    # ------------------------------------------------------------------
    # Integrity: what must be true for a SKU to sit at a stage
    # ------------------------------------------------------------------
    @api.constrains("pipeline_stage_id")
    def _check_pipeline_integrity(self):
        """Every earlier stage must be done, approved when required, and have
        enough hours. This is the guarantee behind the stage gates: it holds
        for the UI, imports and direct ORM writes alike."""
        for project in self.filtered(lambda p: p.is_sku and p.pipeline_stage_id):
            stages = project._pipeline_stages()
            current = project.pipeline_stage_id
            if current not in stages:
                continue
            for stage in stages[: stages.ids.index(current.id)]:
                task = project._task_for(stage)
                message = project._stage_blocker(stage, task)
                if not message and task.state != DONE:
                    message = _("%(stage)s is not finished.", stage=stage.name)
                if message:
                    raise ValidationError(
                        _("%(sku)s cannot be at %(current)s: %(reason)s",
                          sku=project._label(), current=current.name, reason=message)
                    )

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        first_stage = None
        for vals in vals_list:
            if vals.get("is_sku"):
                vals.setdefault("allow_timesheets", True)
                if not vals.get("pipeline_stage_id"):
                    first_stage = first_stage or self._pipeline_stages()[:1]
                    if not first_stage:
                        raise UserError(_("Configure at least one pipeline stage first."))
                    vals["pipeline_stage_id"] = first_stage.id
        projects = super().create(vals_list)
        projects.filtered("is_sku")._create_pipeline_tasks()
        return projects

    def write(self, vals):
        if (
            "pipeline_stage_id" in vals
            and not self.env.su
            and not self.env.context.get(INTERNAL)
        ):
            raise UserError(
                _("Use the Hand Over and Send Back buttons to move a SKU between stages.")
            )
        return super().write(vals)

    def unlink(self):
        skus = self.filtered("is_sku")
        if skus:
            # History records are protected, so purge them with the project.
            history = self.env["project.update"].sudo().with_context(**{INTERNAL: True})
            history.search([("project_id", "in", skus.ids)]).unlink()
            self.env["urbana.sku.handover"].sudo().with_context(**{INTERNAL: True}).search(
                [("project_id", "in", skus.ids)]
            ).unlink()
        # Deleting a SKU deletes its stage tasks, which are otherwise protected.
        return super(ProjectProject, self.with_context(**{INTERNAL: True})).unlink()

    def _create_pipeline_tasks(self):
        stages = self._pipeline_stages()
        vals_list = []
        for project in self:
            manager = project.user_id
            for stage in stages:
                # Until someone is assigned, the project manager owns the task,
                # so a hand over is never stuck on an empty assignee. A stage
                # with a job position still needs a matching person.
                fits = manager and (
                    not stage.job_id or manager.sudo().employee_id.job_id == stage.job_id
                )
                vals_list.append({
                    "name": f"{project._label()} - {stage.name}",
                    "project_id": project.id,
                    "pipeline_stage_id": stage.id,
                    "user_ids": [Command.set(manager.ids if fits else [])],
                    "state": "01_in_progress" if stage == project.pipeline_stage_id else "04_waiting_normal",
                })
        self.env["project.task"].with_context(**{INTERNAL: True}).create(vals_list)

    # ------------------------------------------------------------------
    # Project updates
    # ------------------------------------------------------------------
    def _post_update(self, name, status, body, handover=None):
        self.ensure_one()
        total = len(self._pipeline_stages())
        closed = len(self.tasks.filtered(lambda t: t.state == DONE))
        return self.env["project.update"].with_context(**{INTERNAL: True}).create({
            "name": name,
            "project_id": self.id,
            "status": status,
            "description": body,
            "progress": round(closed * 100 / total) if total else 0,
            "handover_id": handover.id if handover else False,
        })

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_handover_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Hand Over"),
            "res_model": "urbana.handover.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_send_back_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Back"),
            "res_model": "urbana.send.back.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_advance(self, notes=False):
        """Hand the SKU over to the next stage."""
        self.ensure_one()
        if not self.is_sku:
            raise UserError(_("This project is not a SKU."))
        stages = self._pipeline_stages()
        current = self.pipeline_stage_id
        index = stages.ids.index(current.id)
        if index + 1 >= len(stages):
            raise UserError(_("The SKU is already at the last stage."))
        next_stage = stages[index + 1]
        current_task = self._task_for(current)
        next_task = self._task_for(next_stage)
        self._check_can_move(current_task)
        message = self._stage_blocker(current, current_task)
        if message:
            raise UserError(message)
        if not next_task.user_ids:
            raise UserError(
                _("Assign someone to the %(stage)s task first.", stage=next_stage.name)
            )

        # Project users cannot write projects, so after our own permission
        # checks the stage move runs privileged.
        current_task.with_context(**{INTERNAL: True}).write({"state": DONE})
        next_task.with_context(**{INTERNAL: True}).write({"state": "01_in_progress"})
        self.sudo().with_context(**{INTERNAL: True}).write({"pipeline_stage_id": next_stage.id})
        self.env["urbana.sku.handover"]._log(self, current_task, next_task, notes=notes)
        for user in next_task.user_ids:
            next_task.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("%(sku)s handed over to you", sku=self._label()),
                note=notes or "",
                user_id=user.id,
            )
        return True

    def _set_cleanup_state(self, state):
        self.ensure_one()
        self._check_can_move(self._task_for(self.pipeline_stage_id))
        self.sudo().write({"cleanup_state": state})
        return True

    def action_cleanup_start(self):
        return self._set_cleanup_state("in_progress")

    def action_cleanup_done(self):
        return self._set_cleanup_state("done")

    def action_complete(self):
        """Mark the last stage done."""
        self.ensure_one()
        stages = self._pipeline_stages()
        last = stages[-1:]
        if not self.is_sku or self.pipeline_stage_id != last:
            raise UserError(_("Only a SKU at the last stage can be completed."))
        task = self._task_for(last)
        self._check_can_move(task)
        message = self._stage_blocker(last, task)
        if message:
            raise UserError(message)
        task.with_context(**{INTERNAL: True}).write({"state": DONE})
        self._post_update(
            _("%(sku)s: %(stage)s complete", sku=self._label(), stage=last.name),
            "done",
            Markup("<p>{}</p>").format(
                _("All stages are complete. Hours on this stage: %(hours)s.", hours=task.effective_hours)
            ),
        )
        return True

    def action_send_back(self, target, reason):
        """Send the SKU back to an earlier stage, with a mandatory reason."""
        self.ensure_one()
        reason = (reason or "").strip()
        if not reason:
            raise UserError(_("A reason is required to send a SKU back."))
        stages = self._pipeline_stages()
        current = self.pipeline_stage_id
        user = self.env.user
        if not (self.env.su or user.has_group(REVIEWER_GROUP) or user.has_group(MANAGER_GROUP)):
            raise AccessError(_("Only reviewers and project managers can send a SKU back."))
        if current == stages[-1:] and not (self.env.su or user.has_group(MANAGER_GROUP)):
            raise AccessError(_("Only a project manager can send back a SKU from the last stage."))
        if target not in stages or stages.ids.index(target.id) >= stages.ids.index(current.id):
            raise UserError(_("A SKU can only be sent back to an earlier stage."))
        if not target.is_return_target:
            raise UserError(_("%(stage)s cannot be a send back target.", stage=target.name))

        current_task = self._task_for(current)
        target_task = self._task_for(target)
        target_index = stages.ids.index(target.id)
        for stage in stages[target_index:]:
            task = self._task_for(stage)
            task.with_context(**{INTERNAL: True}).write({
                "is_approved": False,
                "approved_by": False,
                "approved_date": False,
                "state": "02_changes_requested" if stage == target else "04_waiting_normal",
            })
        self.sudo().with_context(**{INTERNAL: True}).write({"pipeline_stage_id": target.id})
        self.env["urbana.sku.handover"]._log(
            self, current_task, target_task, reason=reason, is_send_back=True
        )
        for assignee in target_task.user_ids:
            target_task.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("%(sku)s sent back to you", sku=self._label()),
                note=reason,
                user_id=assignee.id,
            )
        return True
