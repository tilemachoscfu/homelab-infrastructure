# Jellyfin appearance profile — 2026-10-09

Jellyfin 10.11.11 and Enhanced 12.11.0.0 retained. Jellyfish is vendored in server Branding Custom CSS at commit 8bee37eeb4fcecf6e852699c118e602713f15eb5, local profile 1.0.1.

- One dark theme with red accents, system fonts, subtle card hover, native Jellyfin branding and visible focus. External CSS/font imports and blur filters removed; native playback controls preserved.
- Static decorative home banner uses existing application artwork. Larger desktop library tiles; mobile/coarse-pointer and reduced-motion rules. TV layout omits the decorative banner.
- Enhanced defaults and the existing viewer profile disable file-size, source, special-format, video-codec and audio-format tags. Resolution, dynamic range, languages, ratings and existing Seerr/Arr integrations remain available.
- Unused home slots explicitly disabled to prevent default duplicate sections. Existing row order retained.
- Four missing images added through the existing TMDb provider, with no original poster replacement or writes to media directories.
- Exact CSS delivery, authenticated API access, shelf/search data, read-only media byte delivery and integration payloads checked. Watch history and protected configurations unchanged. Private backups passed checksum, SQLite integrity and isolated restore checks.
- No browser surface was available: visual rendering, responsive screenshots, client interaction and LG/iPhone playback remain unverified. Per-device Backdrops and Details Banner require client inspection.
- Scoped UI rollback uses private API snapshots and preserves current databases, history and new artwork. Production rollback was not executed; dry-run only.

No service upgrade/restart, new plugin, storage change or unrelated production service change. No live CSS with personal artwork IDs, application configurations, logs, media paths or backups are stored in this repository.

Mobile navigation correction: removed conflicting transparent/headroom header overrides, retained native flex layout and safe-area padding, and applied an opaque surface with readable light tab labels. Only mobile header selectors changed. Backup integrity, isolated database restore, exact CSS delivery, unchanged watch history and rollback dry-run passed; actual after-change browser/iPhone rendering remains unverified.
