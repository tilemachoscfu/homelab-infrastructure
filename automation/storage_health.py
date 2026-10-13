"""Validate storage-monitor responses without exposing endpoint/error details."""

import math
import time


def collect(get, url, clock=time.time):
    """Return a check tuple; the collector's check() isolates fetch failures.

    Missing, future, non-finite or stale timestamps must never report healthy.
    Do not return raw provider data: it can contain private mount paths.
    """
    host = get(url)
    timestamp = host.get("timestamp")
    valid = (
        isinstance(timestamp, (int, float))
        and not isinstance(timestamp, bool)
        and math.isfinite(timestamp)
        and 0 <= clock() - timestamp <= 900
    )
    status = {"healthy": "ok", "ok": "ok", "warning": "warning", "error": "error",
              "critical": "error"}.get(host.get("status"), "error")
    return status if valid else "error", {"response_fresh": valid, "status": status}
