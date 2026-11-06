from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import PipelineCase


@tagged("post_install", "-at_install")
class TestGates(PipelineCase):
    def test_creating_a_sku_creates_one_task_per_stage(self):
        sku = self._make_sku()
        self.assertEqual(sku.pipeline_stage_id, self.s_prelim)
        self.assertEqual(sku.tasks.pipeline_stage_id, self.stages)
        self.assertEqual(self._task(sku, self.s_prelim).state, "01_in_progress")
        self.assertEqual(self._task(sku, self.s_ga).state, "04_waiting_normal")

    def test_a_sku_cannot_be_created_beyond_the_first_stage(self):
        with self.assertRaises(ValidationError):
            self.Project.create({
                "name": "X", "sku_code": "X1", "is_sku": True,
                "pipeline_stage_id": self.s_fab.id,
            })

    def test_advance_moves_stage_and_writes_handover_and_update(self):
        sku = self._make_sku()
        self._log_hours(self._task(sku, self.s_prelim), 2)
        sku.with_user(self.worker).action_advance(notes="over to GA")
        self.assertEqual(sku.pipeline_stage_id, self.s_ga)
        self.assertEqual(self._task(sku, self.s_prelim).state, "1_done")
        self.assertEqual(self._task(sku, self.s_ga).state, "01_in_progress")
        handover = sku.handover_ids
        self.assertEqual(len(handover), 1)
        self.assertEqual((handover.from_stage_id, handover.to_stage_id), (self.s_prelim, self.s_ga))
        self.assertEqual(handover.notes, "over to GA")
        self.assertEqual(handover.hours_snapshot, 2)
        self.assertEqual(handover.from_employee_id, self.worker.employee_id)
        update = handover.update_id
        self.assertEqual(update.handover_id, handover)
        self.assertEqual(update.status, "on_track")
        self.assertEqual(sku.last_update_id, update)
        self.assertEqual(update.user_id, self.worker)

    def test_advance_needs_minimum_hours(self):
        sku = self._make_sku()
        with self.assertRaisesMessage(UserError, "hours"):
            sku.action_advance()
        self.assertEqual(sku.pipeline_stage_id, self.s_prelim)
        self._log_hours(self._task(sku, self.s_prelim), 0.5)
        with self.assertRaisesMessage(UserError, "hours"):
            sku.action_advance()
        self._log_hours(self._task(sku, self.s_prelim), 0.5)
        sku.action_advance()
        self.assertEqual(sku.pipeline_stage_id, self.s_ga)

    def test_advance_needs_an_assignee_on_the_next_stage(self):
        sku = self._make_sku(assign=False)
        self._log_hours(self._task(sku, self.s_prelim))
        with self.assertRaisesMessage(UserError, "Assign someone"):
            sku.action_advance()

    def test_advance_needs_approval_where_required(self):
        sku = self._make_sku()
        self._advance_to(sku, self.s_shop)
        self._log_hours(self._task(sku, self.s_shop))
        with self.assertRaisesMessage(UserError, "approved"):
            sku.action_advance()
        self._task(sku, self.s_shop).with_user(self.reviewer).action_approve()
        sku.action_advance()
        self.assertEqual(sku.pipeline_stage_id, self.s_render)

    def test_write_cannot_skip_stages(self):
        sku = self._make_sku()
        with self.assertRaises(ValidationError):
            sku.write({"pipeline_stage_id": self.s_fab.id})
        with self.assertRaises(ValidationError):
            sku.write({"pipeline_stage_id": self.s_shop.id})
        self.assertEqual(sku.pipeline_stage_id, self.s_prelim)

    def test_write_cannot_move_without_hours(self):
        sku = self._make_sku()
        self._task(sku, self.s_prelim).write({"state": "1_done"})
        with self.assertRaisesMessage(ValidationError, "hours"):
            sku.write({"pipeline_stage_id": self.s_ga.id})

    def test_fabrication_is_blocked_without_approved_renders_and_shop_drawings(self):
        sku = self._make_sku()
        self._advance_to(sku, self.s_review)
        self._log_hours(self._task(sku, self.s_review))
        # break the approvals behind the gate, then try every route to Fabrication
        for stage in (self.s_shop, self.s_render):
            self._task(sku, stage).write({"is_approved": False})
            with self.assertRaisesMessage(ValidationError, "approved"):
                sku.write({"pipeline_stage_id": self.s_fab.id})
            sku.invalidate_recordset()
            with self.assertRaises(ValidationError):
                sku.action_advance()
            sku.invalidate_recordset()
            self.assertEqual(sku.pipeline_stage_id, self.s_review)
            self._task(sku, stage).write({"is_approved": True})

    def test_a_manager_cannot_move_the_stage_by_plain_write(self):
        sku = self._make_sku()
        with self.assertRaisesMessage(UserError, "Hand Over"):
            sku.with_user(self.manager).write({"pipeline_stage_id": self.s_ga.id})

    def test_full_run_to_fabrication_and_completion(self):
        sku = self._make_sku()
        self._advance_to(sku, self.s_fab)
        self.assertEqual(sku.pipeline_stage_id, self.s_fab)
        self.assertEqual(len(sku.handover_ids), 5)
        self.assertTrue(sku.export_ready)
        sku.action_complete()
        self.assertTrue(sku.is_completed)
        self.assertEqual(sku.last_update_id.status, "done")
        self.assertEqual(sku.last_update_id.progress, 100)

    def test_complete_only_at_the_last_stage(self):
        sku = self._make_sku()
        with self.assertRaises(UserError):
            sku.action_complete()

    def test_export_ready_follows_the_stage(self):
        sku = self._make_sku()
        self.assertFalse(sku.export_ready)
        self._advance_to(sku, self.s_ga)
        self.assertTrue(sku.export_ready)

    def test_awaiting_approval_flag(self):
        sku = self._make_sku()
        self.assertFalse(sku.awaiting_approval)
        self._advance_to(sku, self.s_shop)
        self.assertTrue(sku.awaiting_approval)
        self._task(sku, self.s_shop).with_user(self.reviewer).action_approve()
        self.assertFalse(sku.awaiting_approval)
