# Guided setup

Instructions for an agent that sets up a Boss Brain workspace **together with its owner, in a dialog**. Start it with one line in Claude Code, Codex or any agent that can run a shell and fetch a URL:

> Set up Boss Brain for me using https://raw.githubusercontent.com/rawmahn/boss-brain/main/SETUP.md

Run it again inside an existing workspace to finish an interrupted setup or to add repos later.

---

## How to run this (for the agent)

The owner wants a working system, not homework. You run every command; the owner only answers questions.

- **One question per message.** Each comes with a suggested answer or 2–4 options, so the owner can just pick. Use AskUserQuestion when the options are clear.
- **Defaults over questions.** Don't ask what you can find out (git config, `gh`, the repos themselves). Show what you found and ask for a yes.
- **Say what you're doing in one line,** then do it. No walls of text, no long explanations unless asked.
- **Ask before anything visible outside this machine:** creating a GitHub repo, pushing, creating labels. One yes can cover a step.
- **Never touch the owner's code repos** beyond cloning. No commits, issues or labels there without a yes.
- **No secrets in files.** Tokens, passwords and keys never go into `CLAUDE.md`, `repos.yaml` or any note.
- **Write in English** in all files, whatever language the conversation is in (see the Standing rules in [MANUAL.md](MANUAL.md)).
- At the end of each step, tell the owner in one line what now exists.

## Step 0: Where are we?

- If the current folder (or a parent) has `workspace.yaml` and `core/`, this is an existing workspace: check each step below and **resume at the first one that isn't done.**
  - Step 3 is not done while `CLAUDE.md` still has the template's "Add your own standing rules here" line.
  - Step 4 is not done while `repos.yaml` still has `repos: {}`.
- Otherwise, this is a new setup. Ask where the workspace should live and what to call it. Suggest `~/workspace` (or a new folder next to the current one). Never set up inside an existing git repo that isn't a workspace.

## Step 1: Prerequisites

Check, fix what you can, report the rest:

| Check | Fix |
|---|---|
| `git --version` | Ask the owner to install git |
| `python3 --version` | Ask the owner to install Python 3 |
| `python3 -c "import yaml"` | Offer `pip install --user pyyaml` (needed by `sync-repos.sh`) |
| `gh --version` | Ask the owner to install the [GitHub CLI](https://cli.github.com) |
| `gh auth status` | Ask the owner to run `gh auth login` (scope `repo`); this needs their browser |
| `git config user.name` / `user.email` | Ask for the values and set them globally, after a yes |

Don't go on until all checks pass.

## Step 2: Create the workspace

Suggest the values you found and ask for one yes:

- **Owner name:** `git config user.name`
- **GitHub account:** `gh api user --jq .login`
- **Workspace name:** the folder name

Then:

```bash
mkdir -p <path> && cd <path>
git init -b main
git commit --allow-empty -m "Start workspace"
git subtree add --prefix=core https://github.com/rawmahn/boss-brain.git main --squash
core/init.sh --owner "<owner>" --github <account> --name <name>
git add -A && git commit -m "Set up workspace"
```

Then ask before creating the GitHub repo. It must be **private**, since it will hold personal notes:

```bash
gh repo create <name> --private --source . --push
```

Explain in one line why the repo is needed: its issues are the task queue, and cloud sessions clone the workspace from it.

## Step 3: The owner's rules (`CLAUDE.md`)

This file decides how useful agents are, so take a few questions here. Ask them one at a time, suggest answers, and stop when more answers wouldn't change anything:

1. **What do you mainly want agents to do?** For example: code in a few repos, research and docs, ops chores. This shapes the next questions.
2. **What must agents never touch?** For example: specific repos, production, customer data, billing. Suggest "production and anything that deploys to it" as a starting point.
3. **What always needs your OK?** For example: messages to people, dependency upgrades, anything in shared repos. The manual's defaults already cover messages and external repos, so mention that.
4. **Conventions agents should follow everywhere?** For example: commit style, language of docs, branch naming. Skip this if there are none.

Write the answers as short bullets under `## Rules` in `CLAUDE.md`, replacing the template line. Show the result and ask for a yes.

If the owner has long-lived areas of work (a project, a product, a recurring duty), offer to create `workstreams/<area>/README.md` (goal, status, links) plus `notes.md` for each, and list them under `## Workstreams`. Keep it to the ones the owner names.

## Step 4: Repos (`repos.yaml`)

1. List candidates: `gh repo list <account> --limit 50 --json nameWithOwner,isPrivate,pushedAt`. If the owner works in orgs, list those too (`gh api user/orgs --jq '.[].login'`, then `gh repo list <org>`). Show the 10 most recently pushed and let the owner pick. Zero repos is fine: the workspace works on its own.
2. For each picked repo, fill in what you can find and confirm it in one message:
   - `remote`, `path: repos/<name>`, and `branch` from `gh repo view <repo> --json defaultBranchRef`.
   - `pr_policy`: suggest **`pr`** (the agent opens PRs, the owner merges). Offer `push-main` only for private playgrounds, and `read-only` for reference repos.
   - `notes`: what deploys where. Look at the repo's CI (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`) for deploys on push, and suggest a line such as "A push to main deploys staging; prod is manual." The autopilot reads this to stay out of production, so get it right.
   - `tasks: true`: ask whether the repo's issues should join the queue. **Warn if the repo is public:** anyone can open an issue there, and an issue without a status label counts as `ready`. Recommend `tasks: true` for private repos only. If other people work on the repo's issues too (a shared repo), suggest `tasks: assigned`: the agents then take only the issues assigned to the owner, and nobody's agent picks up an unassigned one.
3. Write `repos.yaml` and run `scripts/sync-repos.sh`. Report any clone that failed.

## Step 5: Labels

After a yes:

```bash
scripts/task.sh setup
scripts/task.sh setup <repo>     # for each repo with tasks: true / assigned
```

## Step 6: The first task

Ask: **"What's one small, real thing an agent could do for you this week?"** Offer two or three ideas based on Steps 3 and 4, for example a small fix in a picked repo or a short research note in a workstream.

Shape it with the owner, in the style of the [help-human](skills/help-human/SKILL.md) skill: a clear Goal and a checkable **Done when** (for example "File X has section Y with sources", not "research X"). Then:

```bash
scripts/task.sh new "<title>" --backlog          # prints the number
gh api repos/<account>/<workspace>/issues/<n> -X PATCH -f body="<Goal / Done when / Plan / Next>"
scripts/task.sh set <n> ready
```

(Use `--repo <name>` on `new`, and that repo's path in `gh api`, if the task belongs in a task repo.)

## Step 7: First run, supervised

Offer to run the [autopilot](skills/autopilot/SKILL.md) skill now, in this session, while the owner watches. Afterwards, go through it together:

- **What happened:** the claim, the work, how it landed, the Log comment, the release.
- **What to sharpen:** if the agent hesitated, guessed or asked for something it should have known, add one line to `CLAUDE.md` or the repo's `notes`.
- If the task ended in `in-review`, show the owner how to answer a card: a comment starting with `<!-- answer -->`, then label `ready` again (or `scripts/task.sh set <n> ready`). This also works from the GitHub mobile app.

## Step 8: Running on its own (optional)

Ask whether the owner wants runs on a schedule now, or later once they trust it. Recommend later. If now, offer one of these:

- **Cloud (recommended):** a scheduled task in their agent's cloud offering, for example Claude Code on the web, with the workspace repo as the source and `/autopilot` as the prompt. Their machine can be off. If you have a tool to create scheduled tasks, offer to create it; otherwise, give the exact settings.
- **Local:** a cron or launchd entry such as `0 8-18 * * 1-5 cd <path> && claude -p "/autopilot" >> ~/autopilot.log 2>&1`. Mention that unattended runs can't answer permission prompts. Help the owner allow-list the needed tools (git, gh, `scripts/task.sh`, their test commands, file edits) in the agent's settings instead of skipping permissions, and that the machine must be awake.

## Step 9: Wrap up

Commit and push the workspace. Then give the owner a short summary with:

- what exists now (workspace, repos, first task and its status),
- the three things they'll do from here:
  - **add a task** (or say `/help-human` for a fuzzy idea),
  - **run `/autopilot`** (or let the schedule do it),
  - **answer cards**,
- how to update later: `scripts/core.sh pull`.
