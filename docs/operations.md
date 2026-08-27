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

## Media intake safety and queue hygiene

Treat an executable delivered under a movie or episode name as an unsafe
release, even when the title appears plausible. Arr applications deliberately
refuse to import executable files. Quarantine the file outside every media and
download path, remove the associated torrent from the client, and blocklist the
release so automation can choose a replacement. Never execute the quarantined
file. Keep the quarantine private and recoverable until it is intentionally
disposed of.

Enable rejected-hash synchronization for each Prowlarr-connected Arr
application. This allows a hash already blocklisted by Sonarr, Radarr or Lidarr
to be rejected before it is sent back to the download client.

Completed torrents can occasionally remain in qBittorrent as `missingFiles`
after a successful Arr import. Confirm that the final library file exists and
is registered by the relevant Arr application, then remove only the stale
torrent record with file deletion disabled. Do not remove a record while its
library import is uncertain.

Keep incomplete downloads under a dedicated temporary directory and completed
downloads under a separate completed directory. Final Movies, Shows and Music
libraries should contain only imported media and sidecar metadata. Old
`~uTorrentPartFile` files inside final libraries can trigger repeated ffprobe
errors and should be moved to a dated quarantine after confirming that they are
stale and are not active downloads.

For multi-disc music releases, place a copy of the album artwork in the album's
parent directory as well as disc subdirectories. This gives Subsonic clients a
stable album-level cover and avoids parent-folder artwork lookup failures.

## Torrent connectivity baseline

The qBittorrent listening port must match the VPN provider's forwarded port and
Gluetun's allowed VPN input port. Keep random-port selection and UPnP disabled
behind the VPN. Before tuning connection counts or disk caching, confirm that
the VPN is healthy, DHT has peers, the client reports `connected`, and an active
well-seeded torrent reaches a reasonable transfer rate. Avoid speculative
tuning when those checks already pass.

## Jellyfin hardware acceleration

On the AMD APU host, Jellyfin uses VAAPI through the configured DRM render node.
After image or kernel changes, verify the node from inside the container with
`vainfo` and confirm that H.264 and HEVC decode/encode entry points are present.
Do not change GPU drivers when VAAPI initialization and real playback both
succeed.
