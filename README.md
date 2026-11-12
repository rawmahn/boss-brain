# Boss Brain

*Boss Brain is a code name.*

A personal command center for working with coding agents (Claude Code, Codex, others): one private Git repo that sits above all your code repos and holds your notes, your repo registry, and a task queue that agents pick up on their own.

- **A manual for agents** ([MANUAL.md](MANUAL.md)): how the workspace is laid out, standing rules, how changes land in each repo.
- **A task queue on GitHub issues** (`scripts/task.sh`): statuses as labels, race-safe claims as commits on `claim/<n>` branches, decision cards when an agent needs your answer. One queue across the workspace and any repo marked `tasks: true`.
- **Repo registry** (`repos.yaml` + `scripts/sync-repos.sh`): every repo with its working branch and `pr_policy`.
- **Skills**: `autopilot` (do the next task end to end, unattended) and `help-human` (turn a fuzzy idea into a plan, one question at a time).

Your workspace mounts this repo at `core/` as a [git subtree](https://github.com/git/git/blob/master/contrib/subtree/git-subtree.adoc), so every clone, cloud session and CI job has it with no extra step. Your own notes and rules stay in your workspace; `core/` stays shared.

## Start a workspace

Needs `git`, `python3` (PyYAML recommended), and [`gh`](https://cli.github.com) signed in.

```bash
mkdir my-workspace && cd my-workspace && git init -b main
git commit --allow-empty -m "Start workspace"
git subtree add --prefix=core https://github.com/rawmahn/boss-brain.git main --squash
core/init.sh --owner "Your Name" --github your-account
git add -A && git commit -m "Set up workspace"
gh repo create my-workspace --private --source . --push
```

`init.sh` creates `CLAUDE.md` (your own manual, which reads `core/MANUAL.md` first), `workspace.yaml`, `repos.yaml`, the folders, and links `scripts/` and `.claude/skills/` into `core/`. Then:

1. Add your repos to `repos.yaml` (`tasks: true` on the ones whose issues should be tasks) and run `scripts/sync-repos.sh`.
2. Create the task labels: `scripts/task.sh setup` (and `scripts/task.sh setup <repo>` for each task repo).
3. Open the workspace in your agent and try `scripts/task.sh new "First task"`, then `/autopilot`.

## Updating

```bash
scripts/core.sh pull
```

Customize in your own `CLAUDE.md`, skills and scripts rather than inside `core/`, so pulls merge cleanly.

## Contributing

Port the change into a branch of this repo (rather than pushing your workspace history, which carries your private commits) and open a PR. Maintainers who edit `core/` inside their workspace use `scripts/core.sh push`, described in [MANUAL.md](MANUAL.md#core).

Tests: `python3 -m unittest discover -s scripts -p 'test_*.py'`.

## License

[MIT](LICENSE)
