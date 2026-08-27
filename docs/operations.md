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

## Bazarr subtitle automation

New Radarr movies and Sonarr series must receive a language profile when they
are first synchronized into Bazarr. Keep the default Greek profile enabled for
both media types; otherwise new items can appear in Bazarr with no requested
languages and will never enter the wanted-subtitles queue.

Use more than one provider so a temporary outage or daily quota does not stop
the entire workflow. This installation uses authenticated OpenSubtitles access
plus credential-free Greek-capable fallbacks. Provider credentials stay only
in Bazarr's private configuration.

The movie score threshold permits title-and-year fallback matches when an exact
release match is unavailable. This improves coverage but can occasionally
require subtitle timing adjustment. Keep the stricter series threshold because
episode mismatches are more likely.
