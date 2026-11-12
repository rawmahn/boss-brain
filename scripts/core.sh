#!/bin/bash
# Keep the workspace's core/ (a git subtree of Boss Brain) in sync with upstream.
# See core/MANUAL.md, "Core".
#
#   scripts/core.sh pull            merge the latest upstream into core/ (squashed), re-link scripts and skills
#   scripts/core.sh diff            commits in core/ that upstream doesn't have yet
#   scripts/core.sh check           scan those commits (messages + added lines) against .core-denylist
#   scripts/core.sh push [--no-pr]  maintainers: check, push to sync/<workspace> upstream, open or update the PR
#
# Upstream comes from workspace.yaml: core.remote, core.branch (default main), core.maintainer.
set -euo pipefail

find_root() {
  local start d
  start="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; d="$start"
  while [ "$d" != / ]; do
    if [ -f "$d/repos.yaml" ] || [ -f "$d/workspace.yaml" ]; then echo "$d"; return; fi
    d="$(dirname "$d")"
  done
  echo "$start"
}
ROOT="$(find_root)"
cd "$ROOT"
PREFIX=core
cfg() { python3 "$ROOT/$PREFIX/scripts/workspace.py" "$ROOT" get "$@"; }

REMOTE="$(cfg core.remote)" || { echo "set core.remote in workspace.yaml" >&2; exit 1; }
BRANCH="$(cfg core.branch main)"
NAME="$(cfg name "$(basename "$ROOT")")"
SLUG="$(sed -E 's#^.*github\.com[:/]##; s#\.git$##; s#/$##' <<<"$REMOTE")"

fetch_upstream() {
  git fetch --quiet "$REMOTE" "$BRANCH"
  UPSTREAM="$(git rev-parse FETCH_HEAD)"
}

split() {
  SPLIT="$(git subtree split --prefix="$PREFIX" 2>/dev/null)"
}

outgoing() {  # commits in the split that upstream lacks
  git rev-list "$UPSTREAM..$SPLIT"
}

check() {
  local list="$ROOT/.core-denylist" patterns hits=0
  if [ ! -f "$list" ]; then
    echo "⚠ no .core-denylist in the workspace: nothing to scan against" >&2
    return 0
  fi
  patterns="$(mktemp)"; trap 'rm -f "$patterns"' RETURN
  grep -v -E '^\s*(#|$)' "$list" > "$patterns" || true
  [ -s "$patterns" ] || return 0
  for c in $(outgoing); do
    if git log -1 --format=%B "$c" | grep -i -n -E -f "$patterns" >/dev/null; then
      echo "✗ commit message of $(git log -1 --format='%h %s' "$c") matches .core-denylist" >&2
      hits=1
    fi
  done
  if git diff "$UPSTREAM" "$SPLIT" | grep -E '^\+' | grep -v -E '^\+\+\+ ' | grep -i -n -E -f "$patterns" >&2; then
    echo "✗ the lines above (added in core/) match .core-denylist" >&2
    hits=1
  fi
  if [ "$hits" = 1 ]; then
    echo "Nothing pushed. Fix the content, or amend/reword the commits before they go upstream." >&2
    return 1
  fi
  echo "✓ $(outgoing | wc -l | tr -d ' ') outgoing commit(s) pass .core-denylist"
}

relink() {
  "$ROOT/$PREFIX/init.sh" --link
  if [ -n "$(git status --porcelain -- scripts .claude/skills AGENTS.md)" ]; then
    git add -- scripts .claude/skills AGENTS.md
    git commit --quiet -m "Link new core scripts and skills"
    echo "↪ committed new links"
  fi
}

case "${1:-}" in
  pull)
    git subtree pull --prefix="$PREFIX" "$REMOTE" "$BRANCH" --squash \
      -m "Update core from $SLUG"
    relink
    ;;
  diff)
    fetch_upstream; split
    if [ -z "$(outgoing)" ]; then echo "core/ has nothing upstream lacks"; exit 0; fi
    git log --oneline "$UPSTREAM..$SPLIT"
    ;;
  check)
    fetch_upstream; split; check
    ;;
  push)
    [ "$(cfg core.maintainer false)" = true ] \
      || { echo "only maintainers push core (workspace.yaml core.maintainer: true); see core/MANUAL.md, Core" >&2; exit 1; }
    fetch_upstream; split
    if [ -z "$(outgoing)" ]; then echo "core/ has nothing upstream lacks"; exit 0; fi
    check
    head="sync/$NAME"
    git push --quiet --force "$REMOTE" "$SPLIT:refs/heads/$head"
    echo "⬆ pushed $(outgoing | wc -l | tr -d ' ') commit(s) to $SLUG:$head"
    if [ "${2:-}" != --no-pr ]; then
      pr="$(gh pr list -R "$SLUG" --head "$head" --state open --json url --jq '.[0].url // empty')"
      if [ -z "$pr" ]; then
        pr="$(gh pr create -R "$SLUG" --base "$BRANCH" --head "$head" --title "Sync from $NAME" \
          --body "$(printf 'Core changes made in the %s workspace.\n\nMerge with a **merge commit** (not squash or rebase), or the next sync re-sends these commits.\n\n%s\n' "$NAME" "$(git log --format='- %s' "$UPSTREAM..$SPLIT")")")"
      fi
      echo "PR: $pr"
    fi
    ;;
  *)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
