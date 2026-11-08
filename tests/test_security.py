from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import PipelineCase


@tagged("post_install", "-at_install")
class TestSecurity(PipelineCase):
    def setUp(self):
        super().setUp()
        self.sku = self._make_sku()
        self._advance_to(self.sku, self.s_ga)
        self.handover = self.sku.handover_ids

    def test_handover_cannot_be_edited_or_deleted(self):
        with self.assertRaisesMessage(UserError, "cannot be edited"):
            self.handover.write({"notes": "changed"})
        with self.assertRaisesMessage(UserError, "cannot be deleted"):
            self.handover.unlink()

    def test_generated_updates_cannot_be_edited_or_deleted(self):
        update = self.handover.update_id
        with self.assertRaises(UserError):
            update.with_user(self.manager).write({"name": "changed"})
        with self.assertRaises(UserError):
            update.with_user(self.manager).unlink()

    def test_stage_task_state_cannot_be_set_directly(self):
        shop = self._task(self.sku, self.s_shop)
        for user in (self.worker, self.reviewer, self.manager):
            for state in ("1_done", "03_approved", "02_changes_requested"):
                with self.assertRaisesMessage(UserError, "pipeline buttons"):
                    shop.with_user(user).write({"state": state})
        self.assertEqual(shop.state, "04_waiting_normal")

    def test_other_task_states_and_plain_tasks_stay_free(self):
        shop = self._task(self.sku, self.s_shop)
        shop.with_user(self.worker).write({"state": "04_waiting_normal"})
        plain = self.env["project.task"].create({"name": "plain", "project_id": self.sku.id})
        plain.with_user(self.worker).write({"state": "1_done"})
        self.assertEqual(plain.state, "1_done")

    def test_buttons_still_set_the_locked_states(self):
        self._complete_stage(self.sku)  # GA -> Shop Drawings as the worker's hand over
        shop = self._task(self.sku, self.s_shop)
        shop.with_user(self.reviewer).action_approve()
        self.assertEqual(shop.state, "03_approved")
        self.assertEqual(self._task(self.sku, self.s_ga).state, "1_done")

    def test_stage_task_cannot_be_deleted(self):
        shop = self._task(self.sku, self.s_shop)
        for user in (self.worker, self.reviewer, self.manager):
            with self.assertRaisesMessage(UserError, "cannot be deleted"):
                shop.with_user(user).unlink()
        self.assertTrue(shop.exists())

    def test_a_sku_has_one_task_per_stage(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.env["project.task"].create({
                "name": "second prelim",
                "project_id": self.sku.id,
                "pipeline_stage_id": self.s_prelim.id,
            })

    def test_other_skus_and_plain_tasks_are_not_affected(self):
        other = self._make_sku(code="U102")
        self.assertEqual(len(other.tasks), 6)
        for name in ("one", "two"):
            self.env["project.task"].create({"name": name, "project_id": self.sku.id})

    def test_plain_tasks_can_still_be_deleted(self):
        plain = self.env["project.task"].create({"name": "plain", "project_id": self.sku.id})
        plain.with_user(self.manager).unlink()
        self.assertFalse(plain.exists())

    def test_a_manager_can_delete_the_whole_sku(self):
        self.env["account.analytic.line"].search([("project_id", "=", self.sku.id)]).unlink()
        task_ids = self.sku.tasks.ids
        self.sku.with_user(self.manager).unlink()
        self.assertFalse(self.env["project.task"].browse(task_ids).exists())

    def test_manual_updates_stay_free(self):
        update = self.env["project.update"].with_user(self.manager).create({
            "name": "manual", "project_id": self.sku.id, "status": "on_track",
        })
        update.write({"name": "edited"})
        update.unlink()

    def test_deleting_a_sku_removes_its_history(self):
        handover_id = self.handover.id
        # Odoo refuses to delete tasks that have timesheets, so clear them first.
        self.env["account.analytic.line"].search([("project_id", "=", self.sku.id)]).unlink()
        self.sku.unlink()
        self.assertFalse(self.env["urbana.sku.handover"].browse(handover_id).exists())

    def test_project_users_can_read_but_not_create_handovers(self):
        self.env["urbana.sku.handover"].with_user(self.worker).search([])
        with self.assertRaises(Exception):
            self.env["urbana.sku.handover"].with_user(self.worker).create({
                "project_id": self.sku.id, "from_stage_id": self.s_prelim.id,
                "to_stage_id": self.s_ga.id,
            })

    def test_only_managers_edit_the_stage_configuration(self):
        with self.assertRaises(Exception):
            self.s_ga.with_user(self.worker).write({"min_hours": 0})
        self.s_ga.with_user(self.manager).write({"min_hours": 2})
        self.assertEqual(self.s_ga.min_hours, 2)

    def test_send_back_wizard_only_offers_earlier_return_targets(self):
        self._advance_to(self.sku, self.s_review)
        wizard = self.env["urbana.send.back.wizard"].with_user(self.reviewer).create({
            "project_id": self.sku.id, "target_stage_id": self.s_shop.id, "reason": "x",
        })
        self.assertEqual(wizard.allowed_stage_ids, self.s_prelim + self.s_ga + self.s_shop + self.s_render)
        wizard.action_confirm()
        self.assertEqual(self.sku.pipeline_stage_id, self.s_shop)

    def test_handover_wizard_passes_the_notes_on(self):
        self._log_hours(self._task(self.sku, self.s_ga))
        wizard = self.env["urbana.handover.wizard"].with_user(self.worker).create({
            "project_id": self.sku.id, "notes": "from the wizard",
        })
        wizard.action_confirm()
        self.assertEqual(self._last_handover(self.sku).notes, "from the wizard")

    def test_a_sku_with_logged_hours_cannot_be_deleted(self):
        # Odoo protects timesheets, so such a SKU has to be archived instead.
        self._log_hours(self._task(self.sku, self.s_ga))
        with self.assertRaises(Exception):
            self.sku.unlink()

    def test_assignee_can_update_cleanup_state_but_not_write_the_project(self):
        sku = self.sku.with_user(self.worker)
        sku.action_cleanup_start()
        self.assertEqual(self.sku.cleanup_state, "in_progress")
        sku.action_cleanup_done()
        self.assertEqual(self.sku.cleanup_state, "done")
        with self.assertRaises(Exception):
            sku.write({"cleanup_state": "not_started"})
