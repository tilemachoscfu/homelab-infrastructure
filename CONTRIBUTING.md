# Contributing

Contributions should be small, reviewable and safe for a public repository.

## Before opening a pull request

1. Do not include live credentials, private hostnames, personal paths or data.
2. Use variables and `CHANGE_ME` placeholders for deployment-specific values.
3. Run `./scripts/check-secrets.py`.
4. Validate every changed Compose template.
5. Explain the reason, expected result and rollback path.

## Scope

Good contributions improve documentation, validation, reliability, security or
the portability of existing stacks. Large service additions should begin with
an issue describing dependencies, storage needs and security boundaries.

Never attach unredacted logs, configuration exports or screenshots to an issue
or pull request.
