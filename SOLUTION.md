# SOLUTION: Urbana SKU Pipeline

Odoo 19.0 Community. Module: `urbana_sku_pipeline`. Depends on `project`, `hr`, `hr_timesheet`.

## 1. The problem and the approach

SKU progress lives in daily work updates and a Google Sheet. Nobody can see where a SKU stands, nothing stops a SKU reaching Fabrication unapproved, and handovers are invisible.

The approach: **a SKU is a `project.project`, and each pipeline stage is one `project.task` on it.** The project holds the current stage. Each task holds what belongs to its own stage: the assignee, the approval and the hours.

### Why this shape
| Need | Where it lands |
|---|---|
| A manager and a team per SKU, chatter, a timeline | The project itself |
| A different employee, with a different job position, per stage | `task.user_ids`, plus a job position check |
| Hours per stage, ready for Hubstaff | Timesheet lines on the stage task |
| Approval per stage | Fields on the stage task |
| Progress history | `project.update`, posted automatically |

### The central idea: one invariant
Gates are not scattered across buttons. One constraint on `pipeline_stage_id` states what must be true for a SKU to sit at a stage:

> Every earlier stage has a task that is done, approved if the stage requires approval, and has at least the stage's minimum hours.

That single rule gives sequential movement, the Fabrication gate (Shop Drawings and Rendering are flagged `requires_approval`) and the minimum hours rule. It holds for the UI, imports and direct ORM writes. The buttons (`action_advance`, `action_send_back`) do the bookkeeping and give friendly errors, but they are not what the guarantee depends on.

## 2. How it works

1. A manager creates a SKU (`is_sku`). The module creates one task per configured stage and puts the SKU in the first stage.
2. The project manager owns every stage task until someone else is assigned, so a hand over is never stuck on an empty assignee. The manager then assigns an employee to each stage task. If the stage has a required job position, the assignee must hold it, and the manager is skipped for that stage when they do not.
3. The assignee does the work, posts notes on the task and logs hours.
4. Reviewers approve stages that need it. Approval is only possible for the stage the SKU is currently in.
5. **Hand Over** checks approval, minimum hours and that the next stage has an assignee. It closes the task, moves the stage, writes a handover record, posts a project update and schedules an activity for the next assignee.
6. **Send Back** (reviewers and managers) takes an earlier stage and a mandatory reason. It reopens the target task, resets approvals from the target onward, writes a handover flagged as a send back and posts an at-risk update. The SKU then has to go forward through every gate again.
7. **Send Back from the task.** On the current stage's task (not done), reviewers and managers get one **Send Back** button. Its wizard asks for a mandatory reason and a target stage. The target defaults to the previous stage, and any earlier stage marked as a return target can be chosen. Confirming goes through `action_send_back`, so the integrity rule is untouched and the task states, approval resets, handover record and at-risk update behave exactly as in item 6.
8. **Who is told.** The target stage's assignees get a to-do on its task. An activity is also raised on the SKU project for those assignees, or for the project manager when nobody is assigned. After confirming, the wizard shows a **View Update** button that opens the project update it created.
9. **First stage.** There is no earlier stage to return to, so the target field is hidden. Only that task is reopened (Changes requested, approval cleared), a chatter line is posted and an at-risk project update is logged. No handover record or to-do is created.
10. **Hand Over from the task.** The current stage's task also has a Hand Over button, calling the same project method as the SKU form.
11. **Navigation.** SKUs have their own app (SKUs, Pipeline, Handovers, Configuration). Pipeline is a kanban of every stage task grouped by task state. The standard Projects views hide SKUs by default (a removable "Hide SKUs" filter). A Timesheets tab on the SKU form is shown only to admins in developer mode.
12. **Images.** Each stage task and the SKU form have an **Images** page: a gallery of pictures with a caption, usually screenshots of the work. A picture belongs to a stage task and the SKU page shows those of every stage. Added from the SKU form, a picture defaults to the current stage's task.
13. **What users cannot change directly.** Only the pipeline buttons move a SKU between stages, approve a stage, or set a stage task to done, approved or changes requested. A stage task cannot be deleted (it goes with its SKU) and a SKU has at most one task per stage (a database constraint). Other task states and plain tasks stay free.

## 3. Data model

| Model | Role |
|---|---|
| `urbana.pipeline.stage` | Configuration: order, required `hr.job`, `min_hours`, `requires_approval`, `export_ready`, `is_return_target` |
| `project.project` (extended) | SKU: code, range, current stage, cleanup state, export readiness, Hubstaff project ID |
| `project.task` (extended) | Stage task: stage, approval fields, output link, Hubstaff task ID. Unique per project and stage, not deletable, locked states |
| `urbana.sku.image` | A picture with a caption, kept with a SKU and one of its stage tasks |
| `urbana.sku.handover` | Immutable log of every hand over and send back, with hours at that moment |
| `project.update` (extended) | `handover_id` links the automatic update to its handover |
| `account.analytic.line` (extended) | `hubstaff_entry_id` (unique) and `source` |
| `hr.employee` (extended) | `hubstaff_user_id` |
| `urbana.handover.wizard`, `urbana.send.back.wizard` | Capture notes and the send back target and reason (SKU form) |
| `urbana.request.changes.wizard` | Send Back from a task: reason, target stage, and a link to the update it created |

## 4. Assumptions

1. The six stages are those in the brief. The render team's sub-steps (cleanup, D5, post processing, image management) are work notes, not stages.
2. A SKU is client work, so each SKU is a project with a project manager.
3. Assignees are employees. A stage's required job position is configuration, and is empty by default because position names are unknown.
4. Hours are tracked in Hubstaff. Until that integration exists they are entered manually as timesheet lines.
5. Shop Drawings and Rendering require approval by default. Every stage except Fabrication needs 1 hour by default.
6. A Revit prelim is not export ready, GA drawings and later are. This is configured on the stage.
7. Approvals are per SKU. The render docs approve per batch, which is not modelled.
8. After a send back, hours already logged on reset tasks still count toward their minimum.
9. Only a project manager can send a SKU back from the last stage.
10. The linked Urbana pages describe only the render team's slice of the pipeline. The other stages are my reasoning.
11. The project manager is a sensible first owner of every stage task. Odoo defaults the project manager to the user who creates the SKU.
12. Images are screenshots and other working pictures. They sit next to the task and do not replace progress shown on the Urbana website.

## 5. Trade-offs and alternatives

| Alternative | Why not |
|---|---|
| `mrp` / `stock` | Models physical production and inventory. A SKU here is a design workflow |
| PLM | Enterprise only, and not on OCA as far as I found |
| One task for all stages | Per-stage assignee, hours, approval and Hubstaff mapping would all become custom fields |
| Separate custom SKU model | Loses the project manager, chatter, updates and timesheets that `project` provides |
| Gates only in button methods | Bypassed by imports and ORM writes. The constraint is the guarantee |
| Native task stages as the pipeline | Users can drag cards past a gate. The pipeline position lives on the project instead |
| Separate Request Changes and Send Back on the task | They did almost the same thing, so there is one Send Back. The reviewer picks the stage (usually the previous one) and the integrity rule still decides what is allowed |

## 6. Hubstaff integration (designed, not built)

Hours are the only thing that comes from Hubstaff, and every hand-off point already exists.

| Hubstaff | Odoo | Field |
|---|---|---|
| Project | SKU project | `hubstaff_project_id` |
| Task | Stage task | `hubstaff_task_id` |
| User | Employee | `hubstaff_user_id` |
| Time entry | Timesheet line | `hubstaff_entry_id` (unique), `source = hubstaff` |

A sync job would, per Hubstaff time entry: find the stage task by `hubstaff_task_id`, the employee by `hubstaff_user_id`, skip it if `hubstaff_entry_id` already exists, and otherwise create a timesheet line with `source = hubstaff`. Nothing else in the module changes. The minimum hours rule then becomes trustworthy, because manual entry stops being the only source. The sync must run as a user who can write all timesheets, because assignees only see their own. Hubstaff's API itself was not checked.

## 7. Review needed

The module now does what the brief asks: a SKU moves through the six stages with hours, approval and ownership checked at every hand over, send backs are recorded, and the work is tracked on the SKU. I have reached the point where I need this reviewed before going further, because the rest depends on assumptions I made (section 4) that only the team can confirm. Chiefly:

- the six stages and their gates, taken from the brief and the Urbana pages that describe only the render team's slice (assumptions 1, 5, 6 and 10),
- approval per SKU and not per batch (7),
- how hours count after a send back (8), and who may send a SKU back from the last stage (9),
- who owns each stage task and which job positions the stages require (3 and 11),
- the Hubstaff time sync, which is designed in section 6 but not built until the hours rules are confirmed.

## 8. Known limitations

- The integrity constraint runs when `pipeline_stage_id` changes. Reopening an earlier task afterwards is not re-checked. Task approval and stage fields, and the done, approved and changes requested states, are protected from direct edits to limit this.
- Gates are configuration driven. A manager who turns off `requires_approval` weakens them on purpose.
- Manual hours can be typed to satisfy the minimum until the Hubstaff sync exists.
- A SKU with logged hours cannot be deleted. This is Odoo's own protection of timesheets, so archive the SKU instead.
- `project.task_ids` hides closed tasks, so the module uses the unfiltered `tasks` field everywhere.
- Task `Waiting` states are set by hand and Odoo can recompute them if a task's native stage changes. Native task dependencies would avoid this and are untested here.
- Stages are looked up by order, so reordering stages in the configuration of a SKU already in progress is not supported.

To try it by hand: install the module, open Project > SKUs, create a SKU, assign an employee to each stage task (Stage Tasks tab), log a timesheet line on the task, then use Hand Over. Approve Shop Drawings and Rendering as a user in the Reviewer group, and try Send Back from Technical Drawing Review.

For setup and day-to-day use, see `readme/CONFIGURE.md` and `readme/USAGE.md`.

## 10. Agent-driven testing (2026-11-08)

Besides the unit tests, three AI agents were set loose on a throwaway database (`urbana_agent_test`) with one login per role, using the same actions the buttons call over XML-RPC. No code was changed during the run, and the findings were then triaged.

| Agent | What it did |
|---|---|
| Happy path | Carried one SKU through all six stages, with each role logging hours and notes, getting approvals and handing over, then completed it |
| Request changes | Requested changes on the first stage, a middle stage and after approval, sent back more than one stage, and used the SKU-level send back, then reworked and advanced again |
| Wrong moves | Tried 36 things that should be refused (no hours, no approval, workers approving, skipping stages, direct state and stage writes, deleting tasks, empty reasons) |

The gates held: no stage was ever skipped, and the hours, approval, ownership and reason checks gave clear messages. The runs found these holes, **fixed afterwards** (commits after `48154de`):

- a user could set any stage task to done, approved or changes requested (now locked),
- a stage task could be deleted, which left the SKU stuck (now blocked),
- a second task could be created for a stage, which blocked later hand overs (now one per stage),
- Technical Drawing Review and Fabrication had no assignee, so the hand over into them failed until someone assigned a person (the project manager now owns them by default).

Manual testing of the task form also found that it failed to load after the Send Back merge, because a computed field's method had been deleted. A test now reads the form's computed fields.
