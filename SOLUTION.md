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
2. The manager assigns an employee to each stage task. If the stage has a required job position, the assignee must hold it.
3. The assignee does the work, posts notes on the task and logs hours.
4. Reviewers approve stages that need it. Approval is only possible for the stage the SKU is currently in.
5. **Hand Over** checks approval, minimum hours and that the next stage has an assignee. It closes the task, moves the stage, writes a handover record, posts a project update and schedules an activity for the next assignee.
6. **Send Back** (reviewers and managers) takes an earlier stage and a mandatory reason. It reopens the target task, resets approvals from the target onward, writes a handover flagged as a send back and posts an at-risk update. The SKU then has to go forward through every gate again.
7. **Request Changes** (reviewers and managers, on the current stage's task) asks for a reason and is now a one stage send back: the task goes to Waiting, the previous stage's task to Changes requested, approvals are cleared, the SKU returns to the previous stage and its owner gets a to-do. It reuses `action_send_back`, so the integrity rule is untouched. On the first stage there is nothing earlier, so only that task is reopened and an at-risk project update is logged (no handover record, no to-do).
8. **Task buttons**: Hand Over and Send Back also appear on the current stage's task (not done), calling the same project methods as the SKU form. Send Back keeps its reviewer/manager rule.

## 3. Data model

| Model | Role |
|---|---|
| `urbana.pipeline.stage` | Configuration: order, required `hr.job`, `min_hours`, `requires_approval`, `export_ready`, `is_return_target` |
| `project.project` (extended) | SKU: code, range, current stage, cleanup state, export readiness, Hubstaff project ID |
| `project.task` (extended) | Stage task: stage, approval fields, output link, Hubstaff task ID |
| `urbana.sku.handover` | Immutable log of every hand over and send back, with hours at that moment |
| `project.update` (extended) | `handover_id` links the automatic update to its handover |
| `account.analytic.line` (extended) | `hubstaff_entry_id` (unique) and `source` |
| `hr.employee` (extended) | `hubstaff_user_id` |
| `urbana.handover.wizard`, `urbana.send.back.wizard` | Capture notes and the send back target and reason |

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

## 5. Trade-offs and alternatives

| Alternative | Why not |
|---|---|
| `mrp` / `stock` | Models physical production and inventory. A SKU here is a design workflow |
| PLM | Enterprise only, and not on OCA as far as I found |
| One task for all stages | Per-stage assignee, hours, approval and Hubstaff mapping would all become custom fields |
| Separate custom SKU model | Loses the project manager, chatter, updates and timesheets that `project` provides |
| Gates only in button methods | Bypassed by imports and ORM writes. The constraint is the guarantee |
| Native task stages as the pipeline | Users can drag cards past a gate. The pipeline position lives on the project instead |

## 6. Hubstaff integration (designed, not built)

Hours are the only thing that comes from Hubstaff, and every hand-off point already exists.

| Hubstaff | Odoo | Field |
|---|---|---|
| Project | SKU project | `hubstaff_project_id` |
| Task | Stage task | `hubstaff_task_id` |
| User | Employee | `hubstaff_user_id` |
| Time entry | Timesheet line | `hubstaff_entry_id` (unique), `source = hubstaff` |

A sync job would, per Hubstaff time entry: find the stage task by `hubstaff_task_id`, the employee by `hubstaff_user_id`, skip it if `hubstaff_entry_id` already exists, and otherwise create a timesheet line with `source = hubstaff`. Nothing else in the module changes. The minimum hours rule then becomes trustworthy, because manual entry stops being the only source. The sync must run as a user who can write all timesheets, because assignees only see their own. Hubstaff's API itself was not checked.

## 7. Out of scope or unfinished

- The Hubstaff sync itself.
- Importing the existing Google Sheet, and syncing folder status suffixes (`Cleanup-LH`, `In_Review`).
- Approval per batch.
- Dashboards beyond the kanban, list filters and project updates.
- Per-user record rules beyond the project visibility Odoo already provides.
- Daily work updates are chatter notes on the stage task, not a separate model.

## 8. Known limitations

- The integrity constraint runs when `pipeline_stage_id` changes. Reopening an earlier task afterwards is not re-checked. Task approval and stage fields are protected from direct edits to limit this.
- Gates are configuration driven. A manager who turns off `requires_approval` weakens them on purpose.
- Manual hours can be typed to satisfy the minimum until the Hubstaff sync exists.
- A SKU with logged hours cannot be deleted. This is Odoo's own protection of timesheets, so archive the SKU instead.
- `project.task_ids` hides closed tasks, so the module uses the unfiltered `tasks` field everywhere.
- Task `Waiting` states are set by hand and Odoo can recompute them if a task's native stage changes. Native task dependencies would avoid this and are untested here.
- Stages are looked up by order, so reordering stages in the configuration of a SKU already in progress is not supported.

## 9. Testing

Install and run the tests in a throwaway database:

```bash
cd ~/Devbin/Odoo/OdooCommunity/odoo_v19
direnv exec . python odoo-bin -d urbana_pipeline_test -i urbana_sku_pipeline \
    --test-enable --test-tags /urbana_sku_pipeline --stop-after-init \
    --http-port=8070 --without-demo=all
```

Use `-u` instead of `-i` on later runs. The expected result is `0 failed, 0 error(s)`.

What the tests cover:
- **Gates:** one task per stage, hand over writes a handover and an update, minimum hours, assignee required, approval required, no skipping through `write`, Fabrication blocked without approved renders and shop drawings by every route, plain stage writes blocked for users, full run and completion.
- **Send back:** reason required, valid targets only, approvals reset from the target onward and kept before it, the log and the at-risk update, hours kept, gates apply again afterwards, re-approval required, who may send back.
- **Assignment:** job position match, protected fields, who may approve and hand over.
- **Security:** handovers and generated updates are immutable, wizards, configuration access, cleanup buttons.
- **Hubstaff fields:** duplicate entry rejected, synced hours count toward the minimum.

Sanity check: disabling the integrity constraint makes five of these tests fail.

To try it by hand: install the module, open Project > SKUs, create a SKU, assign an employee to each stage task (Stage Tasks tab), log a timesheet line on the task, then use Hand Over. Approve Shop Drawings and Rendering as a user in the Reviewer group, and try Send Back from Technical Drawing Review.
