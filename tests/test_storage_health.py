"""Offline regression tests; never import/run the live collector."""
import importlib.util
from pathlib import Path
import unittest
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("storage_health", ROOT / "automation/storage_health.py")
storage_health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(storage_health)


class StorageHealthTests(unittest.TestCase):
    def collect(self, value):
        return storage_health.collect(lambda _: value, "unused", clock=lambda: 1000)

    def test_healthy_fresh(self):
        self.assertEqual(self.collect({"status": "healthy", "timestamp": 999})[0], "ok")

    def test_stale_missing_future_and_nonfinite_timestamps_fail_closed(self):
        for value in (None, "999", True, float("nan"), float("inf"), 99, 1001):
            with self.subTest(value=value):
                self.assertEqual(self.collect({"status": "healthy", "timestamp": value})[0], "error")

    def test_age_boundary(self):
        self.assertEqual(self.collect({"status": "healthy", "timestamp": 100})[0], "ok")

    def test_statuses(self):
        for raw, expected in (("warning", "warning"), ("critical", "error"),
                              (None, "error"), ("unexpected", "error")):
            self.assertEqual(self.collect({"status": raw, "timestamp": 999})[0], expected)

    def test_no_private_details_in_response(self):
        _, details = self.collect({"status": "healthy", "timestamp": 999,
                                   "missing_mounts": ["private"], "secret": "private"})
        self.assertNotIn("private", str(details))

    def test_fetch_errors_propagate_to_collector_check(self):
        def fetch(_):
            raise HTTPError("unused", 503, "Unavailable", {}, None)
        with self.assertRaises(HTTPError):
            storage_health.collect(fetch, "unused")


if __name__ == "__main__":
    unittest.main()
