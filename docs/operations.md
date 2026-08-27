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

## Home Assistant HTTP settings

On current Home Assistant releases, HTTP and trusted-proxy settings are managed
from **Settings → System → Network**. After Home Assistant confirms that the
YAML migration is complete, remove the obsolete `http:` block from
`configuration.yaml`; leaving it there produces a repair warning and the block
is ignored.

Before removal, confirm that the stored UI configuration contains the expected
forwarded-header and trusted-proxy settings. Back up both the YAML file and the
HTTP storage record, validate the configuration, then restart only Home
Assistant and verify local and reverse-proxy access.
