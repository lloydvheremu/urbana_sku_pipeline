from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import PipelineCase


@tagged("post_install", "-at_install")
class TestAssignment(PipelineCase):
    def test_assignee_job_must_match_the_stage(self):
        drafter = self.env["hr.job"].create({"name": "Drafter"})
        other = self.env["hr.job"].create({"name": "Artist"})
        self.s_prelim.job_id = drafter
        sku = self._make_sku(assign=False)
        task = self._task(sku, self.s_prelim)
        self.worker.employee_id.job_id = other
        with self.assertRaisesMessage(ValidationError, "job position"):
            task.write({"user_ids": [Command.set(self.worker.ids)]})
        self.worker.employee_id.job_id = drafter
        task.write({"user_ids": [Command.set(self.worker.ids)]})
        self.assertEqual(task.user_ids, self.worker)

    def test_a_stage_without_a_job_accepts_anyone(self):
        self.assertFalse(self.s_ga.job_id)
        sku = self._make_sku()
        self.assertEqual(self._task(sku, self.s_ga).user_ids, self.worker)

    def test_stage_and_approval_fields_are_protected_from_users(self):
        sku = self._make_sku()
        task = self._task(sku, self.s_shop)
        for vals in ({"is_approved": True}, {"approved_by": self.manager.id},
                     {"pipeline_stage_id": self.s_ga.id}):
            with self.assertRaises(UserError):
                task.with_user(self.manager).write(vals)

    def test_only_reviewers_can_approve(self):
        sku = self._make_sku()
        self._advance_to(sku, self.s_shop)
        task = self._task(sku, self.s_shop)
        with self.assertRaises(AccessError):
            task.with_user(self.worker).action_approve()
        task.with_user(self.reviewer).action_approve()
        self.assertTrue(task.is_approved)
        self.assertEqual(task.approved_by, self.reviewer)
        self.assertTrue(task.approved_date)
        self.assertEqual(task.state, "03_approved")

    def test_only_the_current_stage_can_be_approved(self):
        sku = self._make_sku()
        with self.assertRaises(UserError):
            self._task(sku, self.s_shop).with_user(self.reviewer).action_approve()

    def test_a_stage_without_approval_cannot_be_approved(self):
        sku = self._make_sku()
        with self.assertRaisesMessage(UserError, "does not need approval"):
            self._task(sku, self.s_prelim).with_user(self.reviewer).action_approve()

    def test_request_changes_clears_an_approval(self):
        sku = self._make_sku()
        self._advance_to(sku, self.s_shop)
        task = self._task(sku, self.s_shop)
        task.with_user(self.reviewer).action_approve()
        task.with_user(self.reviewer).action_request_changes()
        self.assertFalse(task.is_approved)
        self.assertEqual(task.state, "02_changes_requested")

    def test_only_the_assignee_or_a_reviewer_can_hand_over(self):
        sku = self._make_sku()
        self._log_hours(self._task(sku, self.s_prelim))
        outsider = self._make_user("pl_outsider", ["project.group_project_user"])
        with self.assertRaises(AccessError):
            sku.with_user(outsider).action_advance()
        sku.with_user(self.worker).action_advance()
        self.assertEqual(sku.pipeline_stage_id, self.s_ga)
