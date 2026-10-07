#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || -z "$1" ]]; then
  echo "Usage: $0 \"commit message\" [paths to commit...]" >&2
  exit 2
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
commit_message="$1"
shift

# A scoped update must not publish someone else's previously staged work.
if [[ $# -gt 0 ]] && ! git diff --cached --quiet; then
  echo "Scoped update requires an empty staging area." >&2
  exit 1
fi

./scripts/sync-from-live.py
./scripts/check-secrets.py
if [[ $# -gt 0 ]]; then
  git add -- "$@"
else
  git add --all
fi

if git diff --cached --quiet; then
  echo "No sanitized changes to commit"
  exit 0
fi

git commit -m "$commit_message"
git push
