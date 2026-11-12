#!/bin/bash
# Set up a workspace around core/ (run from anywhere inside it).
#
#   core/init.sh [--owner NAME] [--github ACCOUNT] [--name WORKSPACE]
#       first run: create the missing starter files from core/templates, then link
#   core/init.sh --link
#       only (re)create the links into core/ (scripts, skills, AGENTS.md); core.sh pull runs this
#
# Never overwrites an existing file; a path that exists and isn't a link into core/ is reported and left alone.
set -euo pipefail

CORE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$CORE")"
[ "$(basename "$CORE")" = core ] || { echo "init.sh must live at <workspace>/core/" >&2; exit 1; }
cd "$ROOT"

LINK_ONLY=0 OWNER="" GITHUB="" NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --link) LINK_ONLY=1 ;;
    --owner) OWNER="$2"; shift ;;
    --github) GITHUB="$2"; shift ;;
    --name) NAME="$2"; shift ;;
    *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
  esac
  shift
done

link() {  # link <path> <target relative to the path's folder>
  local path="$1" target="$2"
  if [ -L "$path" ]; then
    [ "$(readlink "$path")" = "$target" ] && return 0
    echo "⚠ $path links to $(readlink "$path"), not $target: left alone" >&2; return 0
  fi
  if [ -e "$path" ]; then echo "⚠ $path exists and isn't a link into core/: left alone" >&2; return 0; fi
  mkdir -p "$(dirname "$path")"
  ln -s "$target" "$path"
  echo "↪ $path -> $target"
}

# Scripts a workspace runs as scripts/<name> (task.py too: workspace scripts may import it).
for f in task.sh task.py sync-repos.sh sync-gdrive.sh core.sh; do
  link "scripts/$f" "../core/scripts/$f"
done
for d in "$CORE"/skills/*/; do
  s="$(basename "$d")"
  link ".claude/skills/$s" "../../core/skills/$s"
done

if [ "$LINK_ONLY" = 0 ]; then
  OWNER="${OWNER:-$(git config user.name || echo Owner)}"
  GITHUB="${GITHUB:-$(gh api user --jq .login 2>/dev/null || echo your-github-account)}"
  NAME="${NAME:-$(basename "$ROOT")}"
  fill() {  # fill <template> <dest>
    [ -e "$2" ] && { echo "· $2 exists: kept"; return 0; }
    mkdir -p "$(dirname "$2")"
    sed -e "s/{{OWNER}}/$OWNER/g" -e "s/{{GITHUB}}/$GITHUB/g" -e "s/{{NAME}}/$NAME/g" "$CORE/templates/$1" > "$2"
    echo "+ $2"
  }
  fill CLAUDE.md CLAUDE.md
  fill workspace.yaml workspace.yaml
  fill repos.yaml repos.yaml
  fill gitignore .gitignore
  fill people.md people/README.md
  fill career.md career/README.md
  fill inbox.md notes/inbox.md
  fill workstreams.md workstreams/README.md
fi
[ -e CLAUDE.md ] && link AGENTS.md CLAUDE.md
exit 0
