# Jellyfin experience — 2026-10-09

Incremental changes after the earlier media optimization:

- Keep Jellyfin 10.11.11 with Intro Skipper 1.10.11.24, Enhanced 12.11.0.0 and IMDb Ratings NG 4.2.0.0. Keep Bazarr 1.6.2 and Seerr 3.5.0 on tested versions. Do not install the server-12 plugin builds on 10.11.
- Enable online metadata providers in Movies, Shows and Collections. Use targeted refreshes and preserve paths, existing artwork and local files.
- Configure authenticated Sonarr/Radarr instances in Enhanced. Enable Downloads with import issues, Calendar, request issue reporting, links back to available library items, and administrator-only Active Streams. Leave automatic requests and Trakt synchronization disabled.
- Keep Greek preferred and English available as fallback. Four missing subtitle files were added, with synchronization checked on private copies. Two negligible offsets were left untouched; two meaningful offsets were corrected. Do not lower the general matching threshold or reset provider quotas.
- Keep Smart subtitle mode: the tested English HI fallback was available but was not automatically selected. The Always-mode experiment was rolled back.
- Keep Intro Skipper at one worker/thread. A two-episode sample found no common intro. A separate four-episode sample generated four native Intro segments in about 19 seconds, with sampled CPU below one core and RAM below 360 MiB. Avoid unrestricted scans while users are watching.
- Web button clicks, actual intro boundaries, physical subtitle alignment and LG/iPhone playback remain unverified. Native segment APIs, Greek WebVTT delivery and authenticated integration payloads passed.
- Protect configuration and SQLite databases with verified timestamped backups. Preserve watch history and existing backups. Do not migrate media or recover intentionally deleted music files.

No service upgrade, restart, storage/network change or unrelated production change occurred in this phase. Private reports, database snapshots, logs, library filenames and integration secrets are deliberately excluded from this export.
