{
    "name": "Urbana SKU Pipeline",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "summary": "Stage-gated SKU pipeline on projects, with handovers and Hubstaff-ready timesheets",
    "description": """
Each SKU is a project and each pipeline stage is a task on it. Moving a SKU
between stages is done through explicit methods that enforce approvals, a
minimum number of hours and job position matching. Every hand over and send
back is logged and posted as a project update. Hours are recorded as timesheet
lines, entered manually for now and written by a Hubstaff sync later.
    """,
    "author": "Urbana",
    "license": "LGPL-3",
    "depends": ["project", "hr", "hr_timesheet"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/pipeline_stage_data.xml",
        "wizard/send_back_wizard_views.xml",
        "views/pipeline_stage_views.xml",
        "views/project_views.xml",
        "views/task_views.xml",
        "views/handover_views.xml",
        "views/menus.xml",
    ],
    "application": False,
    "installable": True,
}
