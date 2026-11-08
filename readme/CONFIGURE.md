# Configure

## Install

The module depends on `project`, `hr` and `hr_timesheet` (all standard Odoo
19 Community). Install **Urbana SKU Pipeline** from Apps. The six pipeline
stages are created on install.

## Users and groups

| Who | Group to give | What they can do |
|---|---|---|
| Stage workers | Project / User (and Timesheets / User to log hours) | Work on the tasks they are assigned to and hand over their own stage |
| Reviewers | **SKU Pipeline / Reviewer** (Settings > Users) | Everything a worker can, plus approve stages, send a SKU back, and hand over any stage |
| Managers | Project / Administrator | Everything a reviewer can, plus send back from the last stage and edit the pipeline stages |

Every person who will take a stage needs an **employee** linked to their user,
because hours are logged on the employee's timesheet.

## Pipeline stages

Open **SKUs > Configuration > Pipeline Stages**. The order of the list is the
order of the pipeline. Each stage has:

| Field | Meaning |
|---|---|
| Name | Stage name. Must be unique. |
| Minimum hours | Hours that must be logged on the stage task before the SKU can leave the stage. Set to 0 to switch the check off. |
| Requires approval | A reviewer must approve the stage task before the SKU can leave the stage. |
| Job position | If set, only employees with this job position can be assigned to the stage task. Leave empty to accept anyone. |
| Ready for export | SKUs sitting in or past this stage count as ready for export. |
| Can be sent back to | Allows a reviewer to send a SKU back to this stage. |

Defaults on install:

| Stage | Min. hours | Approval | Ready for export | Can be sent back to |
|---|---|---|---|---|
| Preliminary Drafting | 1 | no | no | yes |
| GA Drawings | 1 | no | yes | yes |
| Shop Drawings | 1 | yes | yes | yes |
| Rendering | 1 | yes | yes | yes |
| Technical Drawing Review | 1 | no | yes | no |
| Fabrication | 0 | no | yes | no |

The minimum hours are placeholders. Set the values that suit Urbana.

Stages cannot be reordered or added to the middle of a SKU that is already in
progress without checking the SKUs first: each SKU gets one task per stage when
it is created, and a SKU keeps the tasks it was created with.

## Who owns a stage task

When a SKU is created, its **project manager** owns every stage task until
someone else is assigned. A stage with a job position is left unassigned if the
project manager does not hold that job position. A SKU cannot be handed over
into a stage whose task has nobody assigned, so assign the right person to each
stage task on the **Stage Tasks** tab (or from the task itself).

## Hubstaff

Time is tracked in Hubstaff. The live connection is not built, so hours are
entered by hand as timesheet lines. The fields a later sync needs are already
there:

| Odoo record | Field |
|---|---|
| SKU (project) | Hubstaff Project ID |
| Stage task | Hubstaff Task ID (visible to project managers) |
| Employee | Hubstaff User ID |
| Timesheet line | Hubstaff Entry ID (unique) and Source (manual or Hubstaff) |

## Menus and views

- The **SKUs** app has SKUs, Pipeline (every stage task of every SKU, as a
  kanban by task state), Handovers and Configuration.
- SKUs are hidden from the standard Projects views by default through a
  **Hide SKUs** filter. Remove the filter to see them there.
- The **Timesheets** page on the SKU form is shown to administrators in
  developer mode only.
