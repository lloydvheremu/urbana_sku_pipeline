from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import PipelineCase


@tagged("post_install", "-at_install")
class TestRequestChanges(PipelineCase):
    def setUp(self):
        super().setUp()
        self.sku = self._make_sku()

    def _request(self, stage, reason="needs rework", user=None):
        task = self._task(self.sku, stage).with_user(user or self.reviewer)
        return task._request_changes(reason)

    def test_later_stage_is_sent_back_one_stage(self):
        self._advance_to(self.sku, self.s_ga)
        self._task(self.sku, self.s_prelim).write({"user_ids": [(6, 0, self.worker.ids)]})
        self._request(self.s_ga, "wrong grid")
        ga, prelim = self._task(self.sku, self.s_ga), self._task(self.sku, self.s_prelim)
        self.assertEqual(ga.state, "04_waiting_normal")
        self.assertEqual(prelim.state, "02_changes_requested")
        self.assertEqual(self.sku.pipeline_stage_id, self.s_prelim)
        self.assertFalse(ga.is_approved or prelim.is_approved)
        handover = self._last_handover(self.sku)
        self.assertTrue(handover.is_send_back)
        self.assertEqual(handover.reason, "wrong grid")
        self.assertEqual(handover.update_id.status, "at_risk")
        activity = prelim.activity_ids.filtered(lambda a: a.user_id == self.worker)
        self.assertTrue(activity)
        self.assertIn("wrong grid", activity[-1].note)

    def _project_activities(self):
        return self.env["mail.activity"].search(
            [("res_model", "=", "project.project"), ("res_id", "=", self.sku.id)]
        )

    def test_project_activity_goes_to_the_previous_assignee(self):
        self._advance_to(self.sku, self.s_ga)
        self._request(self.s_ga, "wrong grid")
        activities = self._project_activities()
        self.assertEqual(activities.user_id, self.worker)
        self.assertIn("wrong grid", activities.note)

    def test_project_activity_falls_back_to_the_project_manager(self):
        self.sku.user_id = self.manager
        self._advance_to(self.sku, self.s_ga)
        self._task(self.sku, self.s_prelim).user_ids = False
        self._request(self.s_ga, "wrong grid")
        self.assertEqual(self._project_activities().user_id, self.manager)

    def test_first_stage_creates_no_project_activity(self):
        self._request(self.s_prelim, "bad model")
        self.assertFalse(self._project_activities())

    def test_approval_on_the_stage_is_cleared(self):
        self._advance_to(self.sku, self.s_shop)
        self._task(self.sku, self.s_shop).with_user(self.reviewer).action_approve()
        self._request(self.s_shop)
        self.assertFalse(self._task(self.sku, self.s_shop).is_approved)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_ga)

    def test_reason_is_required(self):
        self._advance_to(self.sku, self.s_ga)
        for reason in ("", "  ", False):
            with self.assertRaisesMessage(UserError, "reason"):
                self._request(self.s_ga, reason)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_ga)

    def test_non_reviewer_is_blocked(self):
        self._advance_to(self.sku, self.s_ga)
        with self.assertRaises(AccessError):
            self._request(self.s_ga, user=self.worker)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_ga)

    def test_only_the_current_stage_can_be_reviewed(self):
        self._advance_to(self.sku, self.s_ga)
        with self.assertRaises(UserError):
            self._request(self.s_shop)

    def test_previous_stage_must_be_a_send_back_target(self):
        self._advance_to(self.sku, self.s_ga)
        self.s_prelim.is_return_target = False
        with self.assertRaisesMessage(UserError, "cannot be a send back target"):
            self._request(self.s_ga)

    def test_first_stage_only_reopens_the_task_and_logs_an_update(self):
        handovers = self.env["urbana.sku.handover"].search_count([("project_id", "=", self.sku.id)])
        updates = self.sku.update_ids
        self._request(self.s_prelim, "bad model")
        prelim = self._task(self.sku, self.s_prelim)
        self.assertEqual(prelim.state, "02_changes_requested")
        self.assertEqual(self.sku.pipeline_stage_id, self.s_prelim)
        self.assertEqual(self._task(self.sku, self.s_ga).state, "04_waiting_normal")
        self.assertEqual(
            self.env["urbana.sku.handover"].search_count([("project_id", "=", self.sku.id)]), handovers
        )
        new = self.sku.update_ids - updates
        self.assertEqual(len(new), 1)
        self.assertEqual(new.status, "at_risk")
        self.assertIn("bad model", new.description)
        self.assertFalse(prelim.activity_ids)

    def test_gates_apply_again_after_a_request(self):
        self._advance_to(self.sku, self.s_ga)
        self._request(self.s_ga)
        prelim = self._task(self.sku, self.s_prelim)
        prelim.write({"state": "01_in_progress"})
        self.sku.action_advance(notes="fixed")
        self.assertEqual(self.sku.pipeline_stage_id, self.s_ga)
        # hours already logged still count; shop drawings stays gated by approval
        self._advance_to(self.sku, self.s_shop)
        with self.assertRaises(UserError):
            self.sku.action_advance()

    def test_button_opens_the_wizard(self):
        self._advance_to(self.sku, self.s_ga)
        task = self._task(self.sku, self.s_ga).with_user(self.reviewer)
        action = task.action_request_changes()
        self.assertEqual(action["res_model"], "urbana.request.changes.wizard")
        wizard = self.env["urbana.request.changes.wizard"].with_user(self.reviewer).create(
            {"task_id": task.id, "reason": "via wizard"}
        )
        wizard.action_confirm()
        self.assertEqual(self.sku.pipeline_stage_id, self.s_prelim)


@tagged("post_install", "-at_install")
class TestTaskButtons(PipelineCase):
    def test_task_buttons_delegate_to_the_project(self):
        sku = self._make_sku()
        task = self._task(sku, self.s_prelim)
        for method in ("action_open_handover_wizard", "action_open_send_back_wizard"):
            self.assertEqual(getattr(task, method)(), getattr(sku, method)())

    def test_only_the_current_stage_task_is_flagged(self):
        sku = self._make_sku()
        self.assertTrue(self._task(sku, self.s_prelim).is_current_stage)
        self.assertFalse(self._task(sku, self.s_ga).is_current_stage)
        self._complete_stage(sku)
        self.assertFalse(self._task(sku, self.s_prelim).is_current_stage)
        self.assertTrue(self._task(sku, self.s_ga).is_current_stage)
        self.assertTrue(self._task(sku, self.s_ga).project_is_first_stage is False)
