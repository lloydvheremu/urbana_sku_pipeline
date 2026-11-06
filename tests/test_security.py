from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PipelineCase


@tagged("post_install", "-at_install")
class TestSecurity(PipelineCase):
    def setUp(self):
        super().setUp()
        self.sku = self._make_sku()
        self._advance_to(self.sku, self.s_ga)
        self.handover = self.sku.handover_ids

    def test_handover_cannot_be_edited_or_deleted(self):
        with self.assertRaisesRegex(UserError, "cannot be edited"):
            self.handover.write({"notes": "changed"})
        with self.assertRaisesRegex(UserError, "cannot be deleted"):
            self.handover.unlink()

    def test_generated_updates_cannot_be_edited_or_deleted(self):
        update = self.handover.update_id
        with self.assertRaises(UserError):
            update.with_user(self.manager).write({"name": "changed"})
        with self.assertRaises(UserError):
            update.with_user(self.manager).unlink()

    def test_manual_updates_stay_free(self):
        update = self.env["project.update"].with_user(self.manager).create({
            "name": "manual", "project_id": self.sku.id, "status": "on_track",
        })
        update.write({"name": "edited"})
        update.unlink()

    def test_deleting_a_sku_removes_its_history(self):
        handover_id = self.handover.id
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
        self.assertEqual(self.sku.handover_ids[:1].notes, "from the wizard")
