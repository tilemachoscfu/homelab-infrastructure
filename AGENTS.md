# Homelab repository instructions

After every live homelab configuration change:

1. Keep a timestamped backup before editing.
2. Run `./scripts/sync-from-live.py`.
3. Run `./scripts/check-secrets.py`.
4. Review the diff for private data.
5. Run `./scripts/update-repo.sh "concise change description"` only when the
   change has been verified.

Never add live `.env` files, databases, API keys, credentials, VPN files,
private hostnames, personal media, logs or backup archives.
