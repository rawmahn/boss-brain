#!/bin/bash
# Two-way sync of the workspace's gdrive/ folder with Google Drive (rclone bisync).
# The rclone remote and folder come from workspace.yaml, `gdrive.remote` (e.g. gdrive:Workspace).
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
remote="$(python3 "$ROOT/core/scripts/workspace.py" "$ROOT" get gdrive.remote)" \
  || { echo "set gdrive.remote in workspace.yaml (an rclone remote:path)" >&2; exit 1; }

echo "🔄 Syncing gdrive/ with $remote ..."
rclone bisync "$remote" "$ROOT/gdrive" --verbose
echo "✅ Sync complete!"
