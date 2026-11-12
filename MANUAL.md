# Command Center manual

The base manual for a personal command-center workspace: one repo that sits above all of a person's code repos. **Notes live in the workspace; code lives in the repos.** This file comes from [command-center](README.md), mounted in the workspace at `core/`. The workspace's own `CLAUDE.md` names the owner, adds their rules and **wins wherever the two disagree**.

A workspace has three jobs:

1. **Drive changes across many repos from one place.** Each repo has its own rules (account, working branch, how changes land) in `repos.yaml`.
2. **Hand off work** to agents or teammates, then check the result yourself (diff, CI, the running thing) rather than trusting a summary.
3. **Keep what isn't written down anywhere else:** private context, the owner's own takes, decisions made in calls, gotchas, notes on people. Anything already in a chat thread, ticket, PR or doc gets a link at most, never a retelling.

"The owner" below is the person the workspace belongs to (`workspace.yaml`, `owner`).

## Layout

| Path | Role |
|---|---|
| `CLAUDE.md` | The workspace's own manual: points here first, then the owner's rules, workstreams and recipes. `AGENTS.md` is a symlink to it |
| `core/` | This core (a `git subtree` of command-center). Shared by everyone who uses it; see **Core** below before editing it |
| `workspace.yaml` | Owner name, GitHub account, where core comes from |
| `repos.yaml` | Registry of every repo: remote, local path, account, working branch, `pr_policy`. **Read it before any git work.** |
| `workers.yaml` | *(optional)* Execution engines for a dispatcher; its `workers:` keys are the allowed `worker:<engine>` pins |
| `repos/` | *(gitignored)* Clones, filled by `scripts/sync-repos.sh` |
| `work/` | *(gitignored)* Worktrees for in-flight changes, named `<repo>--<branch>/` |
| `workstreams/<area>/` | Long-lived areas of work: `README.md` (goal, status, links) + `notes.md` |
| `people/` | One file per person: role, context, how to work with them |
| `career/` | Brag log, goals, CV |
| `notes/` | `inbox.md` for quick capture, `YYYY/YYYY-MM-DD.md` daily logs |
| `gdrive/` | *(gitignored, optional)* Local copy of a Google Drive folder, synced with `scripts/sync-gdrive.sh` (rclone). Binaries, scans and sensitive documents go here, never in git |
| `scripts/` | Symlinks into `core/scripts/` (`task.sh`, `sync-repos.sh`, `sync-gdrive.sh`, `core.sh`) plus the workspace's own scripts |
| `.claude/skills/` | Symlinks into `core/skills/` (`autopilot`, `help-human`) plus the workspace's own skills |

## Standing rules

- **Be proactive, but confirm first.** Propose restructuring (stale notes, misfiled content, duplicates) and apply it only after a yes.
- **Capture as you go.** When a session turns up a durable fact, write it to the right file and say so in one line.
- **Don't duplicate the paper trail.** Link to it instead.
- **Add skills sparingly.** A few lines in the manual beat a new skill; add one only for a workflow that repeats often and has non-obvious steps.
- **Work autonomously, but never speak for the owner.** Code, PRs and notes are fine on a claimed task. Messages to other people need the owner's OK; messaging the owner when blocked is fine in a session they are in, but unattended runs never notify them: the issue left `in-review` is the message.
- **Commit the workspace's own changes yourself,** straight to `main`, and push, without asking. origin/main is the shared state. Commit coarse-grained, when a logical chunk is done. If the push is rejected, `git pull --rebase` and push again.
- **Repo-specific instructions win.** Read a repo's own `CLAUDE.md`/`AGENTS.md` before working in it.
- **External repos: ask first.** Any PR, issue or comment on a repo outside the owner's account needs the owner's OK. Own private repos: no need to ask.
- **English in the repos and tasks.** Everything written down in any repo (files, commit messages, code comments) and in tasks (issue titles, bodies, comments, decision cards) is in English, whatever language the session is in. Only verbatim text meant for someone else (a letter draft, a quoted message, an official name) stays in its own language.
- **Portable links.** Relative paths only in markdown, never absolute paths or `file://` URIs.
- **Archive, don't delete.** Old material goes to an `Archive/` folder inside its area.
- **Keep structure simple.** Don't add folders or files the layout above doesn't need.

## Repos and `pr_policy`

Defined at the top of `repos.yaml`. In short: `push-main` (own private repos: commit to the working branch and push), `pr-self-merge` (own public repos), `pr` (the owner reviews and merges), `push-branch`, `fork-only` (external: ask before any upstream PR), `read-only`. A repo's `notes` say what deploys where; read them before pushing.

## Tasks

Tasks are **GitHub issues in the task repos**: the workspace repo itself (the home repo, `origin`) plus every `repos.yaml` entry with `tasks: true`. A task is addressed by its ref: `81` for the home repo, `<repo>#38` for another task repo (`<repo>` = its `repos.yaml` name); every `task.sh` command takes either, and `list`/`next`/`take`/`holds` serve one queue across all task repos. **Everything about a task lives in its own repo** (the issue, its claim branch, its card images), so collaborators on that repo see the whole task without access to the private workspace; in a task repo other than home, the repo itself stands for its workstream (no `ws:` label). `task.sh new ... --ws <repo>` (or `--repo <repo>`) files the task there; `task.sh setup <repo>` creates the labels in a new task repo. An issue is the handoff between many short, cheap sessions, so it stays coarse: **Goal**, **Done when**, **Plan**, **Next** in the body; the **Log** (decisions and gotchas only, link out for detail) goes in comments.

- **Labels:** exactly one status label (below), optionally `p1` / `p3` (urgent / low; no label means p2, `p2` also works), `ws:<workstream>`, `agent:pm`, and at most one `worker:<engine>` (engines: `workers.yaml`). No other labels. Roles and execution engines are independent. Worker tags are strict pins: an unavailable pinned engine means wait. `task.sh worker <n> <engine>|auto` changes only this pin; `new --worker <name>` sets it at creation.
- **Agents:** a `ready` issue is for one of two agents. No agent label: the **developer** ([autopilot](skills/autopilot/SKILL.md)): code, tests, landing changes. `agent:pm`: a **product manager** (a workspace skill, if the workspace has one): product questions answered from user data and feedback, research, options and specs; it writes no code and ends in a decision card or in developer tasks. `task.sh next/take/holds` serve the developer's queue; `--agent pm` serves the PM's. `task.sh new ... --agent pm` makes a PM task, `task.sh assign <n> dev|pm` hands one over.
- **Statuses:** every open issue carries exactly one status label; closing the issue means done. "In progress" is not a status: it is a claim (below), and `task.sh list` shows it.

  | Status | Meaning | Agents |
  |---|---|---|
  | `backlog` | An idea, or not yet specified enough to start | never pick up |
  | `ready` | An agent's turn: Goal and Done when are clear (or **Next** says what to do) | pick up (`take`), by priority, then issue number |
  | `in-review` | The owner's turn: the work can't go on without an answer, a decision or an input only the owner can give (on a shared task repo: the assignee's turn, the owner's when unassigned). `Waiting on:` line at the top of the body says what. Never for finished work (see **Done = landed**) | never; the owner answers and flips it back to `ready` |
  | `on-hold` | Waits for a condition: another issue, an event, a date. `Waiting on:` line states the condition, optional `Check after: YYYY-MM-DD` | re-check the condition every run (`holds`); when it's met, move to `ready` |
  | closed `completed` / `not_planned` | done / dropped | |

  An issue with no status label (e.g. made in the GitHub UI) counts as `ready`. Issues with an active claim are never picked up; claims older than 2 h without refresh are eligible again.
- **Done = landed.** A task is done when its change is on the repo's working branch per `pr_policy` and verified there (tests, CI, staging). Prod deploys are not part of tasks: they happen separately, on their own track. So Done when never includes a prod deploy or a check on prod, and a finished task asks the owner nothing: no "OK to deploy?", no "check it on prod", no "have a look".
- **Decision card.** Moving an issue to `in-review` takes a card (`--card <file>`): a short comment that reads like a slide, so the owner decides at a glance and opens the Log only if they want to. The script refuses a card over 120 words or 5 bullets, and its question becomes the `Waiting on:` line.
  ```markdown
  ### <the question, one line>
  Options: Pop | Glide | Reveal
  Recommend: Pop, it reads best on a phone

  - up to 5 one-line bullets: what is on the table, the trade-off, what each answer leads to
  ![](<image url>)

  [Log](<link>) · [diff](<link>)
  ```
  `Options:` is optional (without it the answer is Yes / No), so is `Recommend:`.
  **Easy on the head.** Write it the way you'd brief a manager: lead with the outcome and what changes for the owner or the user ("the video starts faster"), then the trade-off, in short everyday words, one idea per bullet. No dense jargon, stacked abbreviations or clever phrasing; a technical term is fine when it's the shortest clear way to say it. Code names, file paths and internals go behind the Log link. If a line needs a second read, rewrite it.
  **Show, don't make them dig.** The card carries everything the decision needs: link what was done (the diff, the running thing on staging, an artifact), and when there are options, put a sample next to each one (`- **Pop**: calm, readable ![](<url>)`). `scripts/task.sh upload <n> <file>...` stores images on the `cards` branch of the task's repo and prints URLs to paste; they render on GitHub.
  The owner answers with a comment that starts `<!-- answer -->` (the chosen option or Yes/No, plus an optional note) and moves the issue to `ready`. A comment that starts `<!-- question -->` is a question instead: answer it with a new card and put the issue back to `in-review`. Log comments are for agents: decisions and gotchas, a few lines each, detail behind links.
- **Claims:** a claim says who holds an issue right now; it is separate from the status. It is a commit on branch `claim/<number>` of the issue's own repo, written through `scripts/task.sh`. Each claim/release is a new commit on top of the tip it read, pushed without force, so when two agents race GitHub accepts one push and rejects the other. The branch is never rewritten. Never work on an issue you haven't claimed. Claiming makes the issue `ready`.
- **Stale claims:** a claim older than 2 h with no new commit is stale. `next`, `take` and `holds` include expired claims; listing is read-only. `claim <n>` and `take` take over an expired claim automatically (non-force push, so only one worker wins). `--steal` is accepted for compatibility and never overrides a fresh claim. Re-running `claim` with your own id refreshes it; a worker lasting more than 2 h must refresh before expiry. Always release with `--as <claim-id>` so an old worker cannot release a successor's claim.
- **Dispatchers (optional):** when `AGENT_TASK_NUMBER`, `AGENT_CLAIM_ID` and `AGENT_WORKER` are set, a dispatcher has assigned that one issue to this worker; the worker claims it itself and must not pick another (see the autopilot skill, "Assigned task mode").
- **Moving between statuses:** `release <n> --to <status>` when you let go (no `--to` keeps `ready`, for a partial chunk); `set <n> <status>` changes it without a claim. When you let go of a task: `--done` once the change is landed and verified; `--to in-review --card <file>` only if the work can't go on without the owner; `--to on-hold --waiting-on "<condition>"` if it now waits on something else.
- **One session = one chunk.** Do one reasonable piece, rewrite **Next** in the issue body so a fresh session can start from it, add a Log comment if something was decided, release.
- **Long remote waits:** if the next step waits on something elsewhere (CI, deploy, another issue) for more than ~30 min, release `--to on-hold --waiting-on ... [--check-after YYYY-MM-DD]` instead of holding the claim.
- **Tooling:** the script uses `gh api` (REST) and needs `gh` signed in. Where GraphQL is blocked (some cloud sandboxes), `gh issue ...` does not work; use `gh api`. `scripts/task.sh prune` (deletes claim branches of closed issues) needs a machine that may delete branches.

## Recipes

**Pick up the next task**
```bash
git pull --rebase --autostash
scripts/task.sh list                 # open issues by status, with claims; in-review (needs the owner) on top
scripts/task.sh holds                # on-hold issues to re-check; condition met -> `set <n> ready`
scripts/task.sh take                 # claims the next ready one; prints "<number> <claim id> <title>"
# or: scripts/task.sh next --all      # the whole pickup queue, to look before claiming
# ... work; update the issue's Next, add a Log comment ...
scripts/task.sh release <n> --as <claim id> [--done | --to in-review --card <file> | --to on-hold --waiting-on "..."]
```
Or pick one yourself: `scripts/task.sh claim <n>` (prints your claim id).

**Create a task:** `scripts/task.sh new "<title>" [--priority 1|2|3] [--ws <workstream>] [--backlog]` prints the issue number; it starts as `ready` (`backlog` with `--backlog`, for ideas). Fill in Goal/Done when/Plan/Next right away; if you can't yet, put it in the backlog. Then claim it if you're starting now.

**Change a status by hand:** `scripts/task.sh set <n> <status> [--waiting-on ...] [--check-after ...]`, e.g. `set 7 ready` after answering an `in-review` question.

**Change code in a repo**
1. Look the repo up in `repos.yaml` (branch, `pr_policy`, notes); read its own `CLAUDE.md`/`AGENTS.md`.
2. `scripts/sync-repos.sh <name>` to make sure it's cloned and fetched.
3. For anything beyond a trivial edit, use a worktree: `git -C repos/<name> worktree add ../../work/<name>--<branch> -b <branch> origin/<working-branch>`.
4. Land it per `pr_policy`, then `git -C repos/<name> worktree remove ../../work/<name>--<branch>`.

**Hand off and verify:** put the brief in the issue (Goal, Done when). When the result comes back, check the diff/PR/CI yourself before marking anything done; note what you verified in the Log.

**Add a repo:** add an entry to `repos.yaml`, run `scripts/sync-repos.sh <name>`, commit. Add `tasks: true` to make its issues part of the queue, then `scripts/task.sh setup <name>` once.

**Sync Google Drive:** `scripts/sync-gdrive.sh` (remote set in `workspace.yaml`, `gdrive`).

## Core

`core/` is shared code. Most workspaces only **use** it:

- **Update:** `scripts/core.sh pull` merges the latest command-center into `core/` (one squashed commit), then re-links new scripts and skills. Commit nothing else in that commit.
- **Customize in your own layer, not in `core/`.** Your `CLAUDE.md` overrides this manual; your own skills and scripts sit next to the linked ones. Edits inside `core/` will conflict on the next pull.
- **Contribute:** port the change into a fresh branch of the command-center repo (not your workspace history, so no private commits or messages travel) and open a PR there. Ask the owner first, as with any external repo.

A workspace whose `workspace.yaml` sets `core.maintainer: true` also **pushes** core from inside the workspace:

- Commits that touch `core/` touch nothing else, and their messages are safe to publish: they become public commits in command-center.
- `scripts/core.sh push` splits `core/` out of the workspace history, scans every outgoing commit message and diff for the terms in `.core-denylist` (private, one regex per line), and pushes to the `sync/<workspace>` branch of command-center, opening a PR. `scripts/core.sh diff` shows what is not upstream yet.
- Merge those PRs with a **merge commit** (not squash or rebase), or the next push re-sends the same commits.
