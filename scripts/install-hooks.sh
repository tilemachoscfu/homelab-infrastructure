#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
hook="$repo_dir/.git/hooks/pre-commit"

mkdir -p "$(dirname "$hook")"
printf '#!/usr/bin/env bash\nexec "%s/scripts/check-secrets.py"\n' "$repo_dir" > "$hook"
chmod 0755 "$hook"
echo "Installed pre-commit secret scan"
