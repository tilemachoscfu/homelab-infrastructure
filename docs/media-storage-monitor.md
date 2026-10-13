# Isolate storage-monitor outages

## Problem and live change

The media-health collector fetched storage status outside its existing `check()`
exception boundary. An HTTP 503 aborted the entire run before writing a fresh
report or pushing the other checks. On 2026-10-13 the live collector was changed
to import `storage_health` and replace the unguarded storage fetch with:

```python
check('storage', lambda: storage_health.collect(get, STORAGE_STATUS_URL))
```

`STORAGE_STATUS_URL` above denotes the existing private endpoint, unchanged in
the live call. The private collector/configuration is not published here.
`automation/storage_health.py` is the exact portable helper exported from live.
The existing `check()` wrapper records only the exception class on fetch errors,
then continues. The helper rejects stale (>900 seconds), missing, future and
non-finite timestamps and unknown statuses. It returns only freshness/status,
not private paths from the provider. Existing debounce, push destinations and
alert policy are unchanged.

## Backup and rollback

Before editing, the collector was copied with permissions preserved to
`backup-20261013T070234Z/media_health.py` in its private live directory; `cmp`
verified byte equality. The new helper did not previously exist.

To roll back, restore that verified collector file to `media_health.py` in the
same directory, then syntax-check it before the next timer invocation. The
unused helper can remain in place. No database, container, mount, firewall or
network setting was changed. No container restart is required. Run only the
media-health oneshot if immediate validation is needed. The original collector
will again fail its run if the storage endpoint remains unavailable.

## Verification

- AST syntax validation passed for both live Python files before service start.
- Isolated execution of the actual collector `check()` function with an injected
  HTTP 503 recorded `storage=error`, retained only `failure_type=HTTPError`, and
  successfully ran a subsequent check.
- The live oneshot exited 0, wrote a fresh report, and all seven configured pushes
  succeeded. Storage remained `error` as expected while its endpoint returned
  HTTP 503. This is fault containment, not a repair of that endpoint.
- Six offline regression tests cover healthy, stale, future, missing/non-finite
  timestamps, status mapping, detail redaction and HTTP failure propagation.
- Independent import warnings and backup-health errors were observed and left
  unchanged. Backup cleanup also reports an unrecognized backup directory; its
  conservative preservation policy was not weakened or rerun.

Run `python3 -m unittest discover -s tests -v`. Tests do not contact endpoints or
run the collector. Run the sanitized exporter and secret scan before publishing;
unrelated exported stack drift must not be included in this change.
