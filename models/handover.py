from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .project_project import INTERNAL


class UrbanaSkuHandover(models.Model):
    _name = "urbana.sku.handover"
    _description = "SKU Handover"
    _order = "id desc"

    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    from_stage_id = fields.Many2one("urbana.pipeline.stage", required=True, ondelete="restrict")
    to_stage_id = fields.Many2one("urbana.pipeline.stage", required=True, ondelete="restrict")
    from_employee_id = fields.Many2one("hr.employee")
    to_employee_id = fields.Many2one("hr.employee")
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    notes = fields.Text()
    is_send_back = fields.Boolean()
    reason = fields.Text()
    hours_snapshot = fields.Float(help="Hours logged on the stage task when it was handed over.")
    update_id = fields.Many2one("project.update", ondelete="set null")

    def write(self, vals):
        if not self.env.context.get(INTERNAL):
            raise UserError(_("Handover records cannot be edited."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get(INTERNAL):
            raise UserError(_("Handover records cannot be deleted."))
        return super().unlink()

    @api.model
    def _log(self, project, from_task, to_task, notes=False, reason=False, is_send_back=False):
        """Write the handover record and post the matching project update."""
        user = self.env.user
        to_user = to_task.user_ids[:1]
        handover = self.sudo().with_context(**{INTERNAL: True}).create({
            "project_id": project.id,
            "from_stage_id": from_task.pipeline_stage_id.id,
            "to_stage_id": to_task.pipeline_stage_id.id,
            "from_employee_id": user.sudo().employee_id.id,
            "to_employee_id": to_user.sudo().employee_id.id,
            "notes": notes,
            "is_send_back": is_send_back,
            "reason": reason,
            "hours_snapshot": from_task.effective_hours,
        })
        label = project._label()
        from_stage = from_task.pipeline_stage_id.name
        to_stage = to_task.pipeline_stage_id.name
        who = user.name
        to_name = to_user.name or "-"
        hours = from_task.effective_hours
        if is_send_back:
            name = _("%(sku)s: sent back to %(stage)s", sku=label, stage=to_stage)
            status = "at_risk"
            body = Markup(
                "<p>{}</p><p><b>{}</b> {}</p>"
            ).format(
                _("%(who)s sent the SKU back from %(src)s to %(dst)s (%(to)s).",
                  who=who, src=from_stage, dst=to_stage, to=to_name),
                _("Reason:"), reason,
            )
        else:
            name = _("%(sku)s: %(src)s to %(dst)s", sku=label, src=from_stage, dst=to_stage)
            status = "on_track"
            body = Markup("<p>{}</p><p>{}</p>{}").format(
                _("%(who)s handed over from %(src)s to %(dst)s (%(to)s).",
                  who=who, src=from_stage, dst=to_stage, to=to_name),
                _("Hours logged on %(src)s: %(hours)s", src=from_stage, hours=hours),
                Markup("<p><b>{}</b> {}</p>").format(_("Notes:"), notes) if notes else Markup(""),
            )
        update = project._post_update(name, status, body, handover)
        handover.write({"update_id": update.id})
        return handover
