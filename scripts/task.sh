#!/bin/bash
# Task system CLI: GitHub issues in this repo, claimed via `claim/<number>` branches.
# See core/MANUAL.md "Tasks" for the rules.
#
#   scripts/task.sh list                          open issues by status, with claims
#   scripts/task.sh next [--all] [--ws NAME] [--agent dev|pm]   the ready issue a fresh session should pick up (--all: the whole queue, in order; --ws: only that workstream)
#   scripts/task.sh holds [--ws NAME] [--agent dev|pm]          on-hold issues whose condition is due for a re-check
#   scripts/task.sh take [--as ID] [--agent dev|pm]             claim the next pickable issue (race-safe)
#                         (--agent: whose queue; default dev, the autopilot. pm = issues labeled agent:pm)
#   scripts/task.sh new "<title>" [--priority 1|2|3] [--ws NAME] [--backlog] [--agent pm]
#   scripts/task.sh assign <n> dev|pm             hand an issue to the other agent (swaps the agent:pm label)
#   scripts/task.sh worker <n> <engine>|auto           strict engine pin (engines: workers.yaml); auto removes it
#   scripts/task.sh claim <n> [--as ID] [--steal]
#   scripts/task.sh release <n> [--as ID] [--to STATUS | --done | --dropped]
#                         [--waiting-on TEXT] [--check-after YYYY-MM-DD] [--card FILE]
#   scripts/task.sh set <n> STATUS [--waiting-on TEXT] [--check-after YYYY-MM-DD] [--card FILE]
#                         (in-review needs --card; its question becomes the Waiting on line)
#   scripts/task.sh upload <n> FILE...            store card images on branch `cards` (under <n>/), print their URLs
#   scripts/task.sh prune                         delete claim branches of closed issues (local only)
#
# STATUS: in-review, ready, on-hold, backlog (open); done, dropped (close the issue).
exec python3 "$( dirname "${BASH_SOURCE[0]}" )/task.py" "$@"

