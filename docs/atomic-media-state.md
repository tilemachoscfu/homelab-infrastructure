# Atomic media-health JSON snapshots

The live collector previously truncated and rewrote its debounce state and
reports in place. An interruption or serialization/I/O failure could leave an
invalid JSON file and prevent the next run from loading its debounce counters.

On 2026-10-14 its three JSON writes were switched to the portable
`atomic_json.write_json` helper (exported as `automation/atomic_json.py`). The
helper creates an owner-only temporary file in the destination directory,
serializes and fsyncs its contents, then atomically replaces the destination.
Readers see either the complete previous file or the complete new file.
Normal exceptions remove only the helper's own temporary file. An abrupt kill
can leave a private temporary file, but never a partial published JSON document.
This does not provide an all-files transaction or change notification policy.

## Verification and scope

- Both live Python files were syntax-checked before the collector was run.
- Five regression tests cover initial creation, complete replacement and private
  permissions, serialization failure, fsync/replace failure, and reader visibility.
- Synthetic failures preserve the prior file byte-for-byte and clean their own
  temporary files. Tests never touch live state or send notifications.
- Validate the live oneshot's exit status, JSON freshness and file modes after
  application. Existing unhealthy checks must remain visible, not be suppressed.
- No container, database, network, firewall, SSH, disk or timer configuration was
  changed. Only the media-health collector and its JSON persistence are affected.

## Backup and rollback

The original collector was backed up to
`backup-20261014T0700Z/media_health.py` inside its private live directory, with
permissions preserved and byte equality verified before editing. The new helper
did not previously exist.

Restore that collector file to `media_health.py`, syntax-check it and run only
`media-health.service` (user oneshot) if immediate validation is required. The
unused helper may remain in place. No state-file rollback is necessary: the JSON
format is unchanged. Preserve any temporary files for investigation after a hard
kill; no bulk cleanup or backup deletion is part of this change.
