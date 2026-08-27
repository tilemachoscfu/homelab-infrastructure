# Operations

## Change workflow

1. Back up every configuration file or database before editing it.
2. Make the smallest reversible change.
3. Validate the relevant Compose or application configuration.
4. Check container health and logs.
5. Run the sanitized export and secret scanner.
6. Commit and push only when the scanner succeeds.

## Restore rule

Git is documentation and configuration history, not a backup of live data.
Application databases, media and credentials require separate verified backups.

## Secret rotation

If a real secret is ever committed, removing it in a later commit is not
enough. Rotate the secret immediately and purge it from Git history.
