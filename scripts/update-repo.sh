#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
  echo "Usage: $0 \"commit message\"" >&2
  exit 2
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

./scripts/sync-from-live.py
./scripts/check-secrets.py
git add --all

if git diff --cached --quiet; then
  echo "No sanitized changes to commit"
  exit 0
fi

git commit -m "$1"
git push
