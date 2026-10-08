# Homelab automation

This directory contains sanitized, version-controlled copies of the live
Homelab automation. The export process replaces machine-specific paths,
addresses and credentials with portable variables or runtime lookups.

## Daily health report

`daily-health-report.sh` runs at 08:30 and sends a compact Telegram dashboard
covering Docker health, disk usage and SMART data, temperatures, backups,
systemd services, watchdog state, Ethernet connectivity and pending updates.
It reads the active Telegram notification configuration from Uptime Kuma at
runtime, so no bot token or chat ID is stored in Git.

## Nightly maintenance

`nightly-maintenance.sh` runs as root at 04:00. It waits for the 03:15 backup
lock, updates system packages and reboots only after a successful upgrade.
`install-nightly-maintenance.sh` installs the root-owned executable and cron
entry. `crontab.example` documents the user-level backup, power guard and
health-report schedules.

## Conservative backup cleanup

`backup-cleanup.py` only handles the audited full-snapshot format under an
explicitly approved `HomelabBackups` directory. Its private local policy pins
the mountpoint, filesystem type and UUID; it is never exported to Git. The
recorded source path is audit metadata: changing `/dev/sda3` to `/dev/sdb3`
does not change filesystem identity. Validation requires the live mount UUID
to match, resolves its stable `/dev/disk/by-uuid/` block device, checks that
the mounted source refers to that device and that the opened backup root is
on it. Missing/unverifiable UUIDs, wrong devices, mountpoints or types, and
ambiguous/missing real mounts stop cleanup without deletion. These checks
are repeated immediately before each unlink; checksum and retention rules
remain unchanged.
It hashes every manifest-listed component before making a retention plan.
Completeness and integrity follow the producer's successful final rename and
SHA256 manifest protocol; this does not replace periodic restore exercises.
The container inventory supports conservative protection of the newest set
containing each service; it does not prove that every bind-mounted live state
is covered by the producer. In the current audit, Home Assistant live state
is outside the producer's source root. It is never inspected by cleanup, and
its manual rollback backups remain protected. Audited coverage gaps belong in
the private policy's `coverage_warnings`; these keep the storage health status
at WARNING even when filesystem pressure falls below 80%.
The last verified set for each distinct service mount configuration is also
protected, regardless of age. A newer snapshot with different mount metadata
cannot replace the old mount's restore point. Mount versions are hashes of
stored inventory metadata; live bind sources and volumes are never inspected.

Retention is applied separately to every service in the snapshot inventory:
all snapshots within the rolling last seven days (inclusive), the newest in
each of the four previous completed ISO weeks (Monday–Sunday), and the newest
in each of the three previous completed calendar months. These sets are
combined. Each service's last verified snapshot remains protected regardless
of age, including services absent from newer snapshots. Missing historical
periods cannot be reconstructed by cleanup.

Unknown formats, corrupt/incomplete manifests, additional files, nested trees,
symlinks, hardlinks and future timestamps are preserved. Manual rollback,
migration, Toshiba, application-managed and system backups stay outside the
deletion allowlist. No Docker operations or application-state traversal occur.
The private policy can explicitly pin snapshots with `protected_snapshots`, a
mapping from exact snapshot names to audit reasons; these always survive retention.

Filesystem pressure is measured using available space, including reserved
blocks: below 80% is HEALTHY, 80–85% WARNING, and above 85% CRITICAL. Retention
runs at all levels. Critical pressure additionally allows only producer-marked
`.incomplete-<timestamp>` artifacts older than seven days, with no unknown
files and with a newer verified retained replacement for every listed service
and its recorded mount version. Legacy markers without mount versions are
preserved. The producer captures mount versions before copying and complete
snapshots with a changed start/end mount inventory are preserved as uncertain.
Legacy/unmarked incomplete directories are always preserved. The producer
leaves failures for inspection instead of recursively deleting their contents.

After auditing actual paths, run `backup-cleanup-install.py --backup-root
<verified-root> --mountpoint <verified-mount> --docker-root <verified-docker-root>
--timezone Europe/Athens`. Installation backs up existing files and does not
enable the timer. Review a `--dry-run --verbose --plan-output <private-path>`
before `systemctl --user enable --now backup-cleanup.timer`. For the first real
run, use `--execute --apply-plan <private-path>`; any changed plan is refused.
No mode defaults to execution. The timer runs daily at 06:00 Europe/Athens with
`Persistent=true`; the user must already have `Linger=yes` to run after boot.
For a revised dry-run within one hour, `--verified-plan <previous-plan>` can
reuse its hashes only after every file and directory identity is unchanged.
Real executions always perform fresh SHA256 verification; a cached or forged
preview cannot bypass the fresh plan comparison used by `--apply-plan`.

Cleanup shares the producer/maintenance flock, takes a nonblocking lock and
fails safely if busy. The service uses idle I/O priority, nice 19, and a two-hour
timeout. It never restarts containers, reboots or changes existing permissions.
Deletion uses exact descriptor-relative filenames; no recursive deletion or
shell wildcards are used. Every unlink rechecks the mounted filesystem,
candidate identity and the affected services' verified protected backups.

Persistent JSONL logs and atomic `last-run.json` live under
`~/.local/state/homelab-backup-cleanup/`, outside the producer's backup tree.
Logs include dry-run plans, protected backups, durable deletion intentions,
individual deletions, errors, reclaimed allocated bytes and disk usage before
and after. The 08:30 health report consumes `--health`, checks timer health, and
warns on missing/stale/failed cleanup results or filesystem pressure. It only
previews reports during validation and does not send notifications.

Run `python3 automation/backup-cleanup-tests.py -v` for synthetic safety tests.
Validate shell scripts with `bash -n`, Python with `py_compile`, and units with
`systemd-analyze --user verify`. The private policy, plans, logs and audit
backups must never be committed.
