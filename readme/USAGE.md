# Usage

Each SKU is a project. Each pipeline stage is a task on that project, so the
hours, notes and pictures of a stage stay with that stage. The pipeline is:

Preliminary Drafting > GA Drawings > Shop Drawings > Rendering >
Technical Drawing Review > Fabrication

## Create a SKU

1. Open **SKUs > SKUs** and click **New**.
2. Enter the name and the **SKU code** (unique). Set the **project manager**.
3. Save. Six stage tasks are created, with the first stage in progress.
4. On the **Stage Tasks** tab, assign the person responsible for each stage. By
   default the project manager owns all of them until you do.

## Work on a stage

Open the stage task (from the Stage Tasks tab or **SKUs > Pipeline**).

- **Log hours** on the task's Timesheets tab. Hubstaff will write these later.
- **Write notes** in the chatter as the day's progress.
- **Keep pictures** on the **Images** page, for example screenshots of what you
  did. Click **Add Images**, add a caption and the picture, and save the task.
  The SKU's own Images page shows the pictures of every stage.
- Put a link to the output in **Output Link**.

## Hand over to the next stage

Click **Hand Over** on the task, or on the SKU, and add a note for the next
person. The SKU moves to the next stage only if:

- every earlier stage is done,
- the stage has the minimum hours logged,
- the stage is approved, where approval is required (Shop Drawings and
  Rendering by default),
- the next stage's task has somebody assigned.

Only the assignee, a reviewer or a project manager can hand a stage over. If
something is missing you get a message saying what. On a successful hand over:

- the stage task is marked done and the next one starts,
- a handover record is written (who, to whom, when, notes, hours),
- a project update ("X to Y") is posted,
- the next assignees get a to-do on their task.

## Approve a stage (reviewers)

Open the task of a stage that needs approval and click **Approve**. Only the
stage the SKU is currently in can be approved.

## Send back

A reviewer or project manager clicks **Send Back** on the task (or on the SKU),
chooses the stage to return to (the previous one by default) and gives a
**reason**. The reason is required.

- The stage sent back to becomes **Changes requested**, later stages go back to
  **Waiting**, their approvals are cleared, and the SKU returns to that stage.
- A handover record and an at-risk project update are written.
- The previous stage's assignees (or the project manager) get a to-do on the
  task and on the project. Use **View Update** in the wizard to open the update.
- On the **first** stage there is nothing earlier, so only that task is
  reopened and an at-risk update is logged.
- Only a project manager can send back from the last stage. Stages marked "can
  be sent back to = no" are not offered as targets.

Hours already logged are kept. The stages have to be handed over again, in
order, and approvals redone.

## Finish a SKU

At the last stage (Fabrication), use **Start Cleanup** and **Cleanup Done** if
the SKU needs cleaning up, then **Complete**. Cleanup is for tracking and is
not required to complete.

## What cannot be done

These are refused on purpose, from the screens, imports and the API:

- moving a SKU to another stage by editing it (use Hand Over and Send Back),
- marking a stage task done, approved or changes requested by editing it,
- deleting a stage task (it goes away with its SKU),
- creating a second task for the same stage of a SKU,
- editing or deleting handover records and the project updates the module
  posts.

## Follow the work

- **SKUs > SKUs**: list and kanban by stage, filters (My SKUs, Awaiting
  Approval, Ready for Export, Cleanup Not Done), grouping by stage or product
  range, and the SKU form with Stage Tasks, Handovers and Images.
- **SKUs > Pipeline**: all stage tasks as a kanban grouped by state.
- **SKUs > Handovers**: the full history of hand overs and send backs.
