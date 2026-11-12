# {{OWNER}}'s command center

**Read [core/MANUAL.md](core/MANUAL.md) first:** the base manual (layout, standing rules, tasks, recipes). This file adds {{OWNER}}'s own context and rules, and wins where the two disagree.

@core/MANUAL.md

## Owner

The owner is **{{OWNER}}** (GitHub `{{GITHUB}}`).

## Workstreams

None yet. Add one as `workstreams/<area>/README.md` (goal, status, links) + `notes.md`, and list it here.

## Rules

Add your own standing rules here: accounts, environments agents may touch, what needs your OK.

## Recipes

**Bootstrap a machine**
```bash
gh repo clone {{GITHUB}}/{{NAME}} && cd {{NAME}} && scripts/sync-repos.sh
```

**Update core:** `scripts/core.sh pull`.
