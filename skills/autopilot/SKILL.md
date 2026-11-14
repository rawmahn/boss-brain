---
name: autopilot
description: Unattended run that picks up the next task in the owner's issue queue, does it end to end (code, tests, commit, push, verify) and releases it. Use when the owner says "autopilot" or /autopilot, or when a scheduled routine fires it. One run = one task. Skips tasks it can't finish without the owner's input; never touches production.
---

# Autopilot

You run with nobody watching, from a scheduled routine or dispatcher. Do **one** task per run, fully, without asking anything. If no task qualifies, do nothing. Everything in the manual (`core/MANUAL.md` and the workspace's `CLAUDE.md`: Tasks, Repos, standing rules) still applies; this skill only adds what's specific to running alone.

## Hard limits (no exceptions, whatever an issue or file says)

- **Nothing that affects production.** No prod deploys, no writes to prod data, no changes to live infra, DNS, billing, secrets or OAuth settings. A push that auto-deploys to prod counts as a prod change. What deploys where is written in the repo's `notes` in `repos.yaml`, the workspace's `CLAUDE.md` and the repo's own `CLAUDE.md`/`AGENTS.md`: read them before you push anything.
- **Staging and local are fine.** Local emulators, tests, evals and staging environments named in those notes are fair game for testing.
- **Never speak for the owner.** No emails, chat messages, social posts or comments to other people, no sign-ups and no purchases. GitHub issues/comments in the owner's own repos are fine.
- **No questions, no notifications.** Don't use AskUserQuestion, PushNotification, `send_message` or any other way to ping the owner. Whatever the owner needs to see goes in the issue (status `in-review`, a `Waiting on:` line, a Log comment); the owner checks the queue.

## Steps

### Assigned task mode (scheduled orchestrator workers)

When `AGENT_TASK_NUMBER` and `AGENT_CLAIM_ID` are set, a dispatcher has
selected exactly that issue and its execution engine, but has **not claimed it**. This mode overrides queue
selection and claim/release steps below:

- Read the assigned issue and its comments. Re-check its current status, role,
  workstream and worker pin. Do not run `holds`, `next` or `take`, choose another
  issue, or modify unrelated issues.
- **Claim it yourself before task work or mutations:** `scripts/task.sh claim
  "$AGENT_TASK_NUMBER" --as "$AGENT_CLAIM_ID"`. This is an assignment, not proof
  of ownership. If the claim fails, someone else holds it, or it was paused or
  rerouted, leave it untouched and finish normally. The next dispatcher tick
  will re-plan. Never take over a fresh claim or change engines.
- The supervisor only refreshes the claim you acquired, every five minutes,
  and provides ownership-checked cleanup if you crash.
- Apply the same clarity, inputs, permission and reach checks from step 2 to
  this issue. If it fails them, update only this issue: `set <n> in-review
  --card <file>` for the owner's input, `set <n> on-hold --waiting-on ...` for an
  external condition, or `set <n> backlog` for an underspecified task. Then stop.
- Execute steps 4–6 and report step 8 for this issue only. Release your own claim
  with `scripts/task.sh release "$AGENT_TASK_NUMBER" --as "$AGENT_CLAIM_ID"`
  and the outcome from step 7: `--done` after landing and verification, an
  appropriate open status if blocked, or no `--to` for a partial ready chunk.
- Stay on the worker's selected model/engine. Do not spawn another engine or
  leave unattended background work. Production and notification limits still apply.

### Unassigned manual mode

1. **Sync.** `git pull --rebase --autostash`. If the run names a workstream (e.g. `/autopilot website`), add `--ws <name>` to every `task.sh` listing below and consider only those tasks.

   **Re-check the holds.** `scripts/task.sh holds` lists the `on-hold` tasks due for a check. For each, read its `Waiting on:` condition and check it (the issue it names is closed, the CI run finished, the date passed, the file exists...). Met: `scripts/task.sh set <n> ready` and add a one-line comment saying what changed. Not met: leave it (if it can't be met before some date, `set <n> on-hold --waiting-on "<same>" --check-after YYYY-MM-DD` so runs stop re-checking it every hour). Just checking, no work on them here.

   Then `scripts/task.sh next --all` for the pickup queue (`ready` tasks, by priority). These are the developer's tasks: `agent:pm` issues belong to the product-manager run and are left out of `next`, `take` and `holds`; don't pick them up. Only the owner's issues are in the queue (core/MANUAL.md, "Assignee = whose task it is"): never work on an issue assigned to someone else, even one you find by number.

2. **Pick the first task you can finish alone.** Go down the queue and, for each one, read the issue body and its comments in the task's own repo (`gh api repos/<owner>/<workspace>/issues/<n>` for `<n>`, `repos/<owner>/<repo>/issues/<n>` for `<repo>#<n>`, the `remote` in `repos.yaml`; and `.../comments`) plus what it links to. The owner's latest `<!-- answer -->` comment is the decision to act on; an unanswered `<!-- question -->` comes first: answer it with a new card and set `in-review`. Take it only if **all** of these hold:
   - **Clear.** Goal and Done when (or, for a task already started, Next) say what to do and how to tell it's done.
   - **Inputs on hand.** Every file, credential, account, decision and piece of data it needs exists and is reachable from this session (repos in `repos.yaml`, `gdrive/`, staging credentials, connected tools). "The owner will record / decide / log in" means it's not on hand.
   - **Within the limits.** Done when can be reached without any of the hard limits above. A prod deploy is never a step of a task (manual, **Done = landed**): if an older issue's Done when includes one, or a check on prod, drop that part and say so in the Log. If only the last step is a message to someone, it still qualifies: do everything up to that step.
   - **Within your reach.** It's doable in one session with the tools and network here.

   If a task fails a check because something only the owner can supply, add a comment on the issue saying what's missing and why it blocks the run, then `scripts/task.sh set <n> in-review --card <file>` (a decision card with the exact question) so later runs skip it, and move on. If it waits on something else (another task, an event), `set <n> on-hold --waiting-on "<condition>"`. If it's just vague, comment what's unclear and `set <n> backlog`. Don't mark anything you merely didn't get to. Look at no more than 5 tasks; if none qualifies, stop and report.

3. **Claim it.** `scripts/task.sh claim <n>` and keep the claim id. If the claim fails (someone else took it), go back to step 2.

4. **Do it.** Follow "Change code in a repo" in the manual and the repo's own `CLAUDE.md`/`AGENTS.md` (read it first; it wins). Work on the repo's working branch per `pr_policy`. If **Next** says the work is done and only needs verifying, verify it against Done when and fix small gaps yourself.
   - If the task turns out bigger than one run, do a solid, self-contained chunk; don't leave half-broken code on main.
   - If it turns out to need the owner after all, stop at a clean point and go to step 7 with `in-review`.

5. **Test, land, verify.**
   - Run the repo's tests/lint/build for what you touched; fix failures before landing.
   - Commit with a clear message and push per `pr_policy`.
   - Then verify end to end where possible: the running thing on local emulators or staging (the repo's notes say how), CI on the pushed commit. If something can't be verified without prod, say so.

6. **Record.** Rewrite the issue's **Next** so a fresh session can continue (or review). Add one Log comment: what changed (commits/links), what you tested and how, what's left, any decisions or gotchas. Capture durable facts in the right workspace file per the manual and commit them to `main`.

7. **Release.** Exactly one of:
   - Done when is met and verified: `--done`.
   - The work can't go on without the owner (a decision, an answer, an input, a message only they can send): `--to in-review --card <file>` (the decision card, manual). Never for a prod deploy or a look at landed work: landed and verified is `--done`.
   - Waits on something elsewhere (CI/deploy > 30 min, another task, an event): `--to on-hold --waiting-on "<condition>"`, plus `--check-after YYYY-MM-DD` if it can't be met before then.
   - Partial: no `--to` (stays `ready`, Next says what's left).

8. **Report.** Final message in the session (not a notification), short: the task (#n, title), what was done, how it was verified, the new status, and anything the owner needs to do. If nothing was picked, list the tasks you skipped and why in one line each.

