from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import PipelineCase


@tagged("post_install", "-at_install")
class TestHubstaffFields(PipelineCase):
    def test_timesheets_default_to_manual(self):
        sku = self._make_sku()
        line = self._log_hours(self._task(sku, self.s_prelim))
        self.assertEqual(line.source, "manual")
        self.assertFalse(line.hubstaff_entry_id)

    def test_a_hubstaff_entry_cannot_be_imported_twice(self):
        sku = self._make_sku()
        task = self._task(sku, self.s_prelim)
        self._log_hours(task, hubstaff_entry_id="HS-1", source="hubstaff")
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self._log_hours(task, hubstaff_entry_id="HS-1", source="hubstaff")

    def test_lines_without_an_entry_id_can_repeat(self):
        sku = self._make_sku()
        task = self._task(sku, self.s_prelim)
        self._log_hours(task)
        self._log_hours(task)
        self.assertEqual(task.effective_hours, 2)

    def test_synced_hours_count_toward_the_minimum(self):
        sku = self._make_sku()
        self._log_hours(self._task(sku, self.s_prelim), 1.5, hubstaff_entry_id="HS-2", source="hubstaff")
        sku.action_advance()
        self.assertEqual(sku.pipeline_stage_id, self.s_ga)

    def test_mapping_fields_exist_on_each_model(self):
        sku = self._make_sku()
        sku.hubstaff_project_id = "P1"
        self._task(sku, self.s_ga).hubstaff_task_id = "T1"
        self.worker.employee_id.hubstaff_user_id = "U1"
        self.assertEqual(self.Project.search([("hubstaff_project_id", "=", "P1")]), sku)
