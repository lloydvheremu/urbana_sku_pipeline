from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import PipelineCase

# 1x1 PNG
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


@tagged("post_install", "-at_install")
class TestImages(PipelineCase):
    def setUp(self):
        super().setUp()
        self.sku = self._make_sku()
        self.Image = self.env["urbana.sku.image"]

    def test_an_image_added_on_a_task_belongs_to_its_sku(self):
        task = self._task(self.sku, self.s_prelim)
        image = self.Image.with_user(self.worker).create({"task_id": task.id, "image": PNG, "name": "plan"})
        self.assertEqual(image.project_id, self.sku)
        self.assertEqual(task.image_ids, image)
        self.assertEqual(self.sku.image_ids, image)

    def test_an_image_added_on_the_sku_defaults_to_the_current_stage_task(self):
        self._advance_to(self.sku, self.s_ga)
        image = self.Image.with_user(self.worker).create({"project_id": self.sku.id, "image": PNG})
        self.assertEqual(image.task_id, self._task(self.sku, self.s_ga))
        self.assertEqual(image.stage_id, self.s_ga)

    def test_an_image_can_be_kept_on_an_earlier_stage_task(self):
        self._advance_to(self.sku, self.s_ga)
        prelim = self._task(self.sku, self.s_prelim)
        image = self.Image.create({"project_id": self.sku.id, "task_id": prelim.id, "image": PNG})
        self.assertEqual(image.stage_id, self.s_prelim)

    def test_the_task_must_belong_to_the_same_sku(self):
        other = self._make_sku(code="U102")
        with self.assertRaisesMessage(ValidationError, "same SKU"):
            self.Image.create({
                "project_id": self.sku.id, "task_id": self._task(other, self.s_prelim).id, "image": PNG,
            })

    def test_users_can_remove_their_images_and_the_sku_removes_the_rest(self):
        task = self._task(self.sku, self.s_prelim)
        mine = self.Image.with_user(self.worker).create({"task_id": task.id, "image": PNG})
        mine.unlink()
        self.assertFalse(mine.exists())
        kept = self.Image.create({"task_id": task.id, "image": PNG})
        self.env["account.analytic.line"].search([("project_id", "=", self.sku.id)]).unlink()
        self.sku.unlink()
        self.assertFalse(kept.exists())

    def test_the_forms_show_the_images_page(self):
        for model, xmlid in (
            ("project.project", "urbana_sku_pipeline.urbana_sku_view_form"),
            ("project.task", "project.view_task_form2"),
        ):
            view = self.env[model].get_view(view_id=self.env.ref(xmlid).id, view_type="form")
            self.assertIn("image_ids", view["arch"])
