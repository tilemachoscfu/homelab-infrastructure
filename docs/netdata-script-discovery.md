# Netdata scripts discovery directory

## Observed problem and live fix

The running Netdata scripts.d discovery component logged a missing
`/etc/netdata/scripts.d` directory every minute. Its existing `/etc/netdata`
bind mount was writable and otherwise healthy. On 2026-10-15 only the empty
`scripts.d` directory was created under that existing host configuration mount,
with mode 0755 and the same owner/group as the config parent.

No script, credential or collector configuration was installed. The running
watcher retries automatically; no container restart, recreation or image change
is required. No collector was disabled and unrelated sensor faults were not
suppressed. The empty directory is not exported as a Compose change; this
document records the live prerequisite for future recovery/recreation.

## Validation

- Confirm absence on both host and container before creating it.
- Confirm the new directory is visible/readable inside the container and empty.
- Observe logs across at least two one-minute retry intervals: no new missing
  scripts.d directory errors should appear.
- Confirm Netdata stays healthy, its restart counter is unchanged and the local
  `/api/v1/info` endpoint returns valid JSON.
- Run the sanitized export and secret scan; exclude unrelated stack drift from
  the commit. This change does not repair pre-existing backup/storage warnings
  or hardware sensor faults.

## Pre-change record and rollback

There was no existing directory or file content to back up. A timestamped,
private pre-change record was saved at
`backups/pre-scripts-discovery-20261015T070254Z/rollback.md` under the live Netdata
stack. It records the verified absence, original parent metadata and rollback.
No existing file or parent permission was changed.

To roll back, remove only the newly created `config/scripts.d` directory with
`rmdir` while it remains empty. If another task has since added any files, stop
and inspect; never recursively delete them. No restart is necessary. The
original missing-directory warning will return on the next discovery retry.
