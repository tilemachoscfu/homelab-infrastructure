# Daily SQLite compaction in ntopng

The ntopng 7.0.260918 Community alert-store module runs hourly retention cleanup,
then a full SQLite `VACUUM`. The optional patch in
[examples/ntopng-daily-vacuum.patch](examples/ntopng-daily-vacuum.patch) keeps
every cleanup call and changes only full compaction to the 00 UTC hourly run.
Alerts, RRD recording, database settings and retention preferences keep their
existing behavior. SQLite reuses free pages between compactions; the file may
remain larger and more fragmented until the next daily compaction.

This patch was validated against the immutable image
`ntop/ntopng@sha256:d4958e611ffd6f95e3211a046071e25ce66d5b84e2c0fb6d3227a17383fb6d1c`.
The original module SHA-256 is
`76a1562fa6220a91d6e2a454582b2e3b94e10e61e96a669514bb15c36dbac7d3`;
the patched module SHA-256 is
`3281c7bbef3541dc3643cef4c147410070a6f3da2e2d0caf23e725deae30562e`.
The binary embeds Lua 5.4.6. Lua 5.4 tests of all 24 UTC hours retained every
housekeeping call and reduced VACUUM calls from 24 to one per database.

Before deployment, verify the exact image and original module hash, back up
the Compose file and module, and check SQLite integrity. Extract the original
module to a host configuration directory, apply only the patch, then bind the
result read-only to
`/usr/share/ntopng/scripts/lua/modules/alert_store/alert_store_utils.lua` in the
ntopng service. Adding the mount requires recreating only that service with
`docker compose up -d --no-deps --no-build ntopng` using the correct Compose file.
Preserve the data and Redis mounts.

Validate fresh stored alerts, older alert records, updated RRDs and readable
historical archives, container health, unchanged preferences, and matched CPU
and disk-I/O windows. Compare physical cgroup block-device counters: a device
mapper and its underlying device can report the same writes, so do not add
both. Avoid treating process `write_bytes` as physical disk traffic.

Rollback restores the backed-up Compose file and recreates only ntopng. With
the override mount removed, the pinned image exposes its original module.
Verify its hash and health again. Keep live databases and history in place;
restoring an older database would lose newly collected alerts.

The first production hourly run and a complete 24-hour cycle provide different
levels of evidence. Label daily write savings as projections until a full day
is measured. Required hourly DELETE activity remains after this patch. If the
service is down throughout hour 00 UTC, full compaction waits until the next
00 UTC run. Check compatibility again before upgrading the image: this
read-only overlay would otherwise mask an upstream module update.

SQLite describes compaction and free-page reuse in its
[VACUUM documentation](https://www.sqlite.org/lang_vacuum.html).
