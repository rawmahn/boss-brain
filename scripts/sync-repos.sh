#!/bin/bash
# Clone every repo in repos.yaml that is missing locally, and fetch the ones that exist.
# Never touches working trees of existing checkouts beyond `git fetch`.
# Usage: scripts/sync-repos.sh [name ...]   (no names = all)
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

python3 - "$@" <<'EOF' | while IFS=$'\t' read -r name remote path branch; do
import sys, yaml
reg = yaml.safe_load(open("repos.yaml"))
want = set(sys.argv[1:])
for name, r in reg["repos"].items():
    if want and name not in want:
        continue
    print("\t".join([name, r["remote"], r["path"], r.get("branch", "main")]))
EOF
  if [ -d "$path/.git" ]; then
    echo "↻ $name: fetching"
    git -C "$path" fetch --quiet --all --prune || echo "  ⚠ fetch failed for $name"
  else
    echo "⬇ $name: cloning into $path"
    mkdir -p "$(dirname "$path")"
    git clone --quiet --branch "$branch" "$remote" "$path" || echo "  ⚠ clone failed for $name"
  fi
done
