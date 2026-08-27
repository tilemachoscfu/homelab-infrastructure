# Security policy

## Supported version

Security fixes apply to the latest revision of the `main` branch.

## Reporting a vulnerability or exposure

Do not open a public issue containing credentials, private addresses, personal
paths, VPN configuration or other sensitive data.

Use the repository's **Security** tab to submit a private vulnerability report:

https://github.com/tilemachoscfu/homelab-infrastructure/security/advisories/new

Include only the minimum information needed to reproduce the problem. Redact
all real secret values from logs and screenshots.

## If a secret is committed

Deleting it in a later commit is not sufficient because it remains in Git
history. The response is to:

1. revoke or rotate the exposed credential immediately;
2. remove it from current files;
3. purge it from repository history;
4. verify dependent services and access logs;
5. strengthen the scanner with a regression check.

## Public repository boundaries

This project accepts sanitized templates and documentation only. Live `.env`
files, databases, keys, tokens, backups, logs and personal data are outside the
repository's supported scope.
