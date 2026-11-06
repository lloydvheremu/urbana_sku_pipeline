from contextlib import contextmanager

from odoo import Command
from odoo.tests import TransactionCase


class PipelineCase(TransactionCase):
    """Shared fixtures: stages from the data file, three users with employees."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env["project.project"]
        cls.stages = cls.env["urbana.pipeline.stage"].search([])
        cls.s_prelim, cls.s_ga, cls.s_shop, cls.s_render, cls.s_review, cls.s_fab = cls.stages
        cls.manager = cls._make_user("pl_manager", ["project.group_project_manager"])
        cls.reviewer = cls._make_user("pl_reviewer", ["urbana_sku_pipeline.group_urbana_reviewer"])
        cls.worker = cls._make_user(
            "pl_worker", ["project.group_project_user", "hr_timesheet.group_hr_timesheet_user"]
        )

    @classmethod
    def _make_user(cls, login, group_xmlids):
        user = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@example.com",
            "group_ids": [Command.link(cls.env.ref(x).id) for x in group_xmlids],
        })
        employee = cls.env["hr.employee"].create({"name": login, "user_id": user.id})
        user.invalidate_recordset()
        assert user.employee_id == employee
        return user

    # -- helpers ---------------------------------------------------------
    def _make_sku(self, code="U101", assign=True):
        sku = self.Project.create({"name": f"{code} Shelter", "sku_code": code, "is_sku": True})
        if assign:
            sku.tasks.write({"user_ids": [Command.set(self.worker.ids)]})
        return sku

    def _task(self, sku, stage):
        return sku._task_for(stage)

    def _log_hours(self, task, hours=1.0, **extra):
        return self.env["account.analytic.line"].create({
            "name": "work",
            "task_id": task.id,
            "project_id": task.project_id.id,
            "employee_id": self.worker.employee_id.id,
            "unit_amount": hours,
            **extra,
        })

    def _complete_stage(self, sku):
        """Do what is needed to leave the current stage, then hand over."""
        stage = sku.pipeline_stage_id
        task = self._task(sku, stage)
        if task.effective_hours < stage.min_hours:
            self._log_hours(task, stage.min_hours)
        if stage.requires_approval and not task.is_approved:
            task.with_user(self.reviewer).action_approve()
        sku.action_advance(notes="ok")

    def _advance_to(self, sku, stage):
        while sku.pipeline_stage_id != stage:
            self._complete_stage(sku)

    @contextmanager
    def assertRaisesMessage(self, exception, pattern):
        """assertRaises (which rolls back to a savepoint) plus a message check.
        unittest's assertRaisesRegex does not roll back, so it can leave a
        half-applied write behind."""
        with self.assertRaises(exception) as cm:
            yield
        self.assertRegex(str(cm.exception), pattern)

    def _last_handover(self, sku):
        return self.env["urbana.sku.handover"].search(
            [("project_id", "=", sku.id)], order="id desc", limit=1
        )
