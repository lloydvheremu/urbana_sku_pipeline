from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import PipelineCase


@tagged("post_install", "-at_install")
class TestSendBack(PipelineCase):
    def setUp(self):
        super().setUp()
        self.sku = self._make_sku()
        self._advance_to(self.sku, self.s_review)

    def _send_back(self, target, reason="dimension wrong", user=None):
        sku = self.sku.with_user(user or self.reviewer)
        return sku.action_send_back(target, reason)

    def test_a_reason_is_required(self):
        for reason in ("", "   ", False):
            with self.assertRaisesRegex(UserError, "reason"):
                self._send_back(self.s_shop, reason)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_review)

    def test_target_must_be_an_earlier_return_target(self):
        for target in (self.s_review, self.s_fab):
            with self.assertRaises(UserError):
                self._send_back(target)
        self.s_ga.is_return_target = False
        with self.assertRaisesRegex(UserError, "cannot be a send back target"):
            self._send_back(self.s_ga)

    def test_send_back_resets_approvals_from_the_target_onward(self):
        self._send_back(self.s_shop)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_shop)
        shop, render = self._task(self.sku, self.s_shop), self._task(self.sku, self.s_render)
        self.assertFalse(shop.is_approved)
        self.assertFalse(render.is_approved)
        self.assertEqual(shop.state, "02_changes_requested")
        self.assertEqual(render.state, "04_waiting_normal")
        self.assertEqual(self._task(self.sku, self.s_review).state, "04_waiting_normal")
        # earlier stages are untouched
        self.assertEqual(self._task(self.sku, self.s_ga).state, "1_done")
        self.assertEqual(self._task(self.sku, self.s_prelim).state, "1_done")

    def test_sending_back_to_rendering_keeps_the_shop_drawing_approval(self):
        self._send_back(self.s_render)
        self.assertTrue(self._task(self.sku, self.s_shop).is_approved)
        self.assertFalse(self._task(self.sku, self.s_render).is_approved)
        self.assertFalse(self.sku.awaiting_approval and False)
        self.assertTrue(self.sku.awaiting_approval)

    def test_send_back_is_logged_with_the_reason(self):
        self._send_back(self.s_shop, "wrong dimension on door")
        handover = self.sku.handover_ids[:1]
        self.assertTrue(handover.is_send_back)
        self.assertEqual(handover.reason, "wrong dimension on door")
        self.assertEqual((handover.from_stage_id, handover.to_stage_id), (self.s_review, self.s_shop))
        update = handover.update_id
        self.assertEqual(update.status, "at_risk")
        self.assertIn("wrong dimension on door", update.description)
        self.assertEqual(update.handover_id, handover)

    def test_hours_are_kept_on_reset_tasks(self):
        before = self._task(self.sku, self.s_render).effective_hours
        self.assertTrue(before)
        self._send_back(self.s_shop)
        self.assertEqual(self._task(self.sku, self.s_render).effective_hours, before)

    def test_after_a_send_back_the_gates_apply_again(self):
        self._send_back(self.s_shop)
        with self.assertRaises(ValidationError):
            self.sku.write({"pipeline_stage_id": self.s_fab.id})
        with self.assertRaises(ValidationError):
            self.sku.write({"pipeline_stage_id": self.s_render.id})

    def test_after_a_send_back_the_sku_must_be_approved_again(self):
        self._send_back(self.s_shop)
        with self.assertRaisesRegex(UserError, "approved"):
            self.sku.action_advance()
        self._task(self.sku, self.s_shop).with_user(self.reviewer).action_approve()
        self.sku.action_advance()
        self.assertEqual(self.sku.pipeline_stage_id, self.s_render)
        with self.assertRaisesRegex(UserError, "approved"):
            self.sku.action_advance()

    def test_only_reviewers_and_managers_can_send_back(self):
        with self.assertRaises(AccessError):
            self._send_back(self.s_shop, user=self.worker)
        self._send_back(self.s_shop, user=self.manager)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_shop)

    def test_only_a_manager_can_send_back_from_the_last_stage(self):
        self.sku.action_advance()  # review -> fabrication (hours already met)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_fab)
        with self.assertRaises(AccessError):
            self._send_back(self.s_render, user=self.reviewer)
        self._send_back(self.s_render, user=self.manager)
        self.assertEqual(self.sku.pipeline_stage_id, self.s_render)

    def test_cannot_send_back_from_the_first_stage(self):
        sku = self._make_sku("U102")
        with self.assertRaises(UserError):
            sku.with_user(self.reviewer).action_send_back(self.s_prelim, "why")

    def test_send_back_notifies_the_target_assignee(self):
        self._send_back(self.s_shop, "fix it")
        activities = self._task(self.sku, self.s_shop).activity_ids
        self.assertTrue(activities.filtered(lambda a: a.note and "fix it" in a.note))
