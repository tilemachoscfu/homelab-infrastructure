#!/usr/bin/env python3
"""Safety regression tests using synthetic backups only."""
from datetime import datetime, timedelta
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location("cleanup", Path(__file__).with_name("backup-cleanup.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
NOW = datetime(2026, 10, 7, 12, tzinfo=ZoneInfo("Europe/Athens"))


def record(stamp, services=("app",)):
    return {"name": stamp.strftime("%Y-%m-%dT%H%M%S"), "timestamp": stamp.isoformat(),
            "services": list(services)}


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "HomelabBackups"
        self.root.mkdir()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()
        self.config = {"backup_root": str(self.root), "state_dir": str(self.state),
                       "lock_file": str(Path(self.tmp.name) / ".backup.lock"),
                       "timezone": "Europe/Athens"}
        self.identity = c.signature(self.root.stat())[:2]

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self, stamp, services=("app",)):
        name = stamp.strftime("%Y-%m-%dT%H%M%S")
        path = self.root / name
        path.mkdir()
        for filename in c.BASE_FILES:
            (path / filename).write_bytes(b"synthetic backup component")
        (path / "docker-inspect.json").write_text(json.dumps([{"Name": "/" + s} for s in services]))
        (path / "SHA256SUMS").write_text("".join(
            hashlib.sha256((path / f).read_bytes()).hexdigest() + "  ./" + f + "\n"
            for f in sorted(c.BASE_FILES)))
        return path

    def plan(self, percent=50):
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value={"usage_percent": percent}):
            return c.build_plan(self.config, NOW)

    def execute(self, plan):
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value=plan["filesystem_before"]):
            return c.execute(self.config, plan, c.Log(self.state, NOW))

    def test_daily_inclusive_boundary(self):
        records = [record(NOW - timedelta(days=d)) for d in range(12)]
        reasons, _ = c.retention(records, NOW)
        for d in range(8):
            self.assertIn("daily:7-days", reasons[records[d]["name"]])

    def test_four_completed_iso_weeks(self):
        records = [record(NOW - timedelta(days=d)) for d in range(40)]
        reasons, _ = c.retention(records, NOW)
        weeks = {r for rs in reasons.values() for r in rs if r.startswith("weekly:")}
        self.assertEqual(len(weeks), 4)
        self.assertIn("weekly:2026-09-07", weeks)

    def test_three_previous_calendar_months(self):
        records = [record(NOW.replace(month=m, day=5)) for m in (6, 7, 8, 9)]
        reasons, _ = c.retention(records, NOW)
        months = {r for rs in reasons.values() for r in rs if r.startswith("monthly:")}
        self.assertEqual(months, {"monthly:2026-07", "monthly:2026-08", "monthly:2026-09"})

    def test_months_cross_year_boundary(self):
        now = NOW.replace(year=2027, month=1)
        records = [record(NOW.replace(month=m, day=5)) for m in (9, 10, 11, 12)]
        reasons, _ = c.retention(records, now)
        self.assertEqual({r for rs in reasons.values() for r in rs if r.startswith("monthly:")},
                         {"monthly:2026-10", "monthly:2026-11", "monthly:2026-12"})

    def test_sole_old_backup_protected(self):
        old = self.snapshot(NOW - timedelta(days=500))
        plan = self.plan()
        self.assertEqual(plan["selected"], [])
        self.assertEqual(plan["anchors"]["app"], old.name)

    def test_service_missing_from_new_snapshot_protected(self):
        old = self.snapshot(NOW - timedelta(days=500), ("removed-service", "app"))
        self.snapshot(NOW, ("app",))
        plan = self.plan()
        self.assertEqual(plan["selected"], [])
        self.assertEqual(plan["anchors"]["removed-service"], old.name)

    def test_invalid_newest_cannot_replace_valid_old_backup(self):
        old = self.snapshot(NOW - timedelta(days=500))
        latest = self.snapshot(NOW)
        (latest / "docker-configs.tar.gz").write_bytes(b"corruption")
        plan = self.plan()
        self.assertEqual(plan["anchors"]["app"], old.name)
        self.assertEqual(plan["selected"], [])
        self.assertTrue(plan["errors"])

    def test_symlink_file_and_directory_preserved(self):
        old = self.snapshot(NOW - timedelta(days=500))
        (old / "CONTENTS.txt").unlink()
        (old / "CONTENTS.txt").symlink_to("/etc/passwd")
        (self.root / "2020-01-01T000000").symlink_to(old, target_is_directory=True)
        self.assertEqual(self.plan()["selected"], [])

    def test_ancestor_symlink_rejected(self):
        link = Path(self.tmp.name) / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            with c.directory(link):
                pass

    def test_manifest_traversal_duplicate_missing_rejected(self):
        for raw in [b"a" * 64 + b"  ../outside\n", b"a" * 64 + b"  CONTENTS.txt\n" * 2, b""]:
            with self.assertRaises(c.Unsafe):
                c.parse_manifest(raw, c.BASE_FILES)

    def test_hardlinks_preserved(self):
        old = self.snapshot(NOW - timedelta(days=500))
        os.link(old / "CONTENTS.txt", Path(self.tmp.name) / "outside-hardlink")
        self.snapshot(NOW)
        self.assertEqual(self.plan()["selected"], [])

    def test_unknown_nested_file_preserved(self):
        old = self.snapshot(NOW - timedelta(days=500))
        (old / "new-service").mkdir()
        self.snapshot(NOW)
        self.assertEqual(self.plan()["selected"], [])

    def test_dry_plan_does_not_delete(self):
        old = self.snapshot(NOW - timedelta(days=500))
        self.snapshot(NOW)
        plan = self.plan()
        self.assertEqual([r["name"] for r in plan["selected"]], [old.name])
        self.assertTrue(old.exists())
        self.assertGreater(plan["estimated_reclaimed_bytes"], 0)

    def test_successful_deletion_matches_plan_and_preserves_last(self):
        old = self.snapshot(NOW - timedelta(days=500))
        latest = self.snapshot(NOW)
        plan = self.plan()
        deleted, reclaimed, errors = self.execute(plan)
        self.assertEqual(deleted, [old.name])
        self.assertEqual(reclaimed, plan["estimated_reclaimed_bytes"])
        self.assertEqual(errors, [])
        self.assertTrue(latest.exists())
        self.assertFalse(old.exists())
        events = [json.loads(x)["event"] for x in next(self.state.glob("*.jsonl")).read_text().splitlines()]
        self.assertEqual(events.count("delete_intent"), 11)
        self.assertEqual(events.count("deleted_file"), 11)

    def test_anchor_modified_after_plan_aborts_without_deletion(self):
        old = self.snapshot(NOW - timedelta(days=500))
        latest = self.snapshot(NOW)
        plan = self.plan()
        (latest / "CONTENTS.txt").write_bytes(b"changed")
        deleted, reclaimed, errors = self.execute(plan)
        self.assertEqual(deleted, []); self.assertEqual(reclaimed, 0)
        self.assertTrue(errors); self.assertEqual(len(list(old.iterdir())), 11)

    def test_candidate_changed_after_plan_aborts(self):
        old = self.snapshot(NOW - timedelta(days=500))
        self.snapshot(NOW)
        plan = self.plan()
        (old / "extra").write_bytes(b"unknown")
        self.assertEqual(self.execute(plan)[0], [])

    def test_mount_identity_change_aborts_without_deletion(self):
        old = self.snapshot(NOW - timedelta(days=500))
        self.snapshot(NOW)
        plan = self.plan()
        with patch.object(c, "check_mount", return_value=(0, 0)):
            deleted, reclaimed, errors = c.execute(self.config, plan, c.Log(self.state, NOW))
        self.assertEqual(deleted, []); self.assertEqual(reclaimed, 0)
        self.assertTrue(errors); self.assertTrue(old.exists())

    def mount_config(self):
        return {**self.config, "filesystem": {
            "target": str(self.root.parent), "source": "/dev/sda3",
            "fstype": "fuseblk", "uuid": "ABCD-1234"}}

    def mounted_row(self):
        return {**self.mount_config()["filesystem"], "source": "/dev/sdb3"}

    def check_rows(self, rows, device=None):
        result = SimpleNamespace(stdout=json.dumps({"filesystems": rows}))
        with patch.object(c.subprocess, "run", return_value=result), patch.object(
                c, "uuid_device", return_value=self.identity[0] if device is None else device):
            return c.check_mount(self.mount_config())

    def test_mount_device_renumbering_sda3_to_sdb3_accepted(self):
        self.assertEqual(self.check_rows([self.mounted_row()]), self.identity)

    def test_autofs_row_ignored_when_real_uuid_mount_exists(self):
        autofs = {"target": str(self.root.parent), "source": "systemd-1",
                  "fstype": "autofs", "uuid": None}
        self.assertEqual(self.check_rows([autofs, self.mounted_row()]), self.identity)

    def test_mount_uuid_missing_or_mismatched_rejected(self):
        for uuid in (None, "", "WRONG-5678"):
            with self.subTest(uuid=uuid), self.assertRaises(c.Unsafe):
                self.check_rows([{**self.mounted_row(), "uuid": uuid}])

    def test_unmounted_filesystem_rejected(self):
        for rows in ([], [{"target": str(self.root.parent), "source": "systemd-1",
                           "fstype": "autofs", "uuid": None}],
                     [{"target": "/", "source": "/dev/sdb3",
                       "fstype": "fuseblk", "uuid": "ABCD-1234"}]):
            with self.subTest(rows=rows), self.assertRaises(c.Unsafe):
                self.check_rows(rows)

    def test_mount_type_or_target_change_and_ambiguous_rows_rejected(self):
        row = self.mounted_row()
        for rows in ([{**row, "fstype": "ext4"}], [{**row, "target": "/other"}],
                     [row, row]):
            with self.subTest(rows=rows), self.assertRaises(c.Unsafe):
                self.check_rows(rows)

    def test_root_opened_on_different_device_rejected(self):
        with self.assertRaises(c.Unsafe):
            self.check_rows([self.mounted_row()], device=self.identity[0] + 1)

    def test_uuid_resolver_accepts_same_block_device_under_new_name(self):
        node = SimpleNamespace(st_mode=stat.S_IFBLK | 0o600, st_rdev=123)
        with patch.object(c.os, "stat", return_value=node) as lookup:
            self.assertEqual(c.uuid_device("ABCD-1234", "/dev/sdb3"), 123)
        self.assertEqual(lookup.call_args_list[0].args[0], Path("/dev/disk/by-uuid/ABCD-1234"))
        self.assertEqual(lookup.call_args_list[1].args[0], "/dev/sdb3")

    def test_uuid_resolver_missing_device_rejected(self):
        with patch.object(c.os, "stat", side_effect=FileNotFoundError), self.assertRaises(c.Unsafe):
            c.uuid_device("ABCD-1234", "/dev/sdb3")

    def test_uuid_resolver_wrong_device_or_nonblock_rejected(self):
        block = SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=123)
        for node in (SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=456),
                     SimpleNamespace(st_mode=stat.S_IFREG, st_rdev=123)):
            with self.subTest(node=node), patch.object(c.os, "stat", side_effect=[block, node]):
                with self.assertRaises(c.Unsafe):
                    c.uuid_device("ABCD-1234", "/dev/sdb3")

    def test_unverifiable_uuid_and_source_rejected(self):
        for uuid, source in ((None, "/dev/sdb3"), ("", "/dev/sdb3"),
                             ("../escape", "/dev/sdb3"), ("ABCD-1234", None),
                             ("ABCD-1234", "tmpfs")):
            with self.subTest(uuid=uuid, source=source), self.assertRaises(c.Unsafe):
                c.uuid_device(uuid, source)

    def test_findmnt_failure_preserves_backup_files(self):
        old = self.snapshot(NOW - timedelta(days=500))
        with patch.object(c.subprocess, "run", side_effect=c.subprocess.CalledProcessError(1, "findmnt")):
            with self.assertRaises(c.subprocess.CalledProcessError):
                c.build_plan(self.mount_config(), NOW)
        self.assertEqual(len(list(old.iterdir())), 11)

    def test_uuid_mismatch_during_execution_deletes_nothing(self):
        old = self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        plan = self.plan()
        result = SimpleNamespace(stdout=json.dumps({"filesystems": [
            {**self.mounted_row(), "uuid": "WRONG-5678"}]}))
        with patch.object(c.subprocess, "run", return_value=result):
            deleted, reclaimed, errors = c.execute(self.mount_config(), plan, c.Log(self.state, NOW))
        self.assertEqual(deleted, []); self.assertEqual(reclaimed, 0)
        self.assertTrue(errors); self.assertEqual(len(list(old.iterdir())), 11)

    def test_unmarked_incomplete_never_deleted_even_critical(self):
        self.snapshot(NOW)
        (self.root / ".incomplete-2020-01-01T000000").mkdir()
        self.assertEqual(self.plan(99)["selected"], [])

    def disposable(self):
        p = self.root / ".incomplete-2020-01-01T000000"
        p.mkdir()
        (p / c.MARKER).write_text(json.dumps({"protocol": "homelab-full-v1", "disposable": True,
                                            "services": ["app"],
                                            "bindings": c.binding_versions('[{"Name":"/app"}]')}))
        (p / "docker-configs.tar").write_bytes(b"partial copy")
        for f in p.iterdir():
            os.utime(f, (NOW.timestamp() - 10 * 86400,) * 2)
        return p

    def test_marked_disposable_only_critical_with_newer_valid_backup(self):
        self.snapshot(NOW)
        p = self.disposable()
        self.assertEqual(self.plan(85)["selected"], [])
        plan = self.plan(85.001)
        self.assertEqual([r["name"] for r in plan["selected"]], [p.name])
        self.assertEqual(self.execute(plan)[0], [p.name])

    def test_disposable_with_uncovered_service_protected(self):
        self.snapshot(NOW, ("other",))
        self.disposable()
        self.assertEqual(self.plan(99)["selected"], [])

    def test_pressure_boundaries(self):
        self.assertEqual([c.pressure(x) for x in (79.99, 80, 85, 85.01)],
                         ["HEALTHY", "WARNING", "WARNING", "CRITICAL"])

    def test_successful_cleanup_at_83_percent_remains_warning(self):
        self.snapshot(NOW)
        (self.state / "last-run.json").write_text(json.dumps({
            "timestamp": NOW.isoformat(), "mode": "execute", "root": str(self.root),
            "deleted": [], "errors": [], "reclaimed_bytes": 0}))
        result = SimpleNamespace(stdout=json.dumps({"filesystems": [self.mounted_row()]}))
        with patch.object(c.subprocess, "run", return_value=result), patch.object(
                c, "uuid_device", return_value=self.identity[0]), patch.object(
                c, "usage", return_value={"usage_percent": 83}):
            health = c.health(self.mount_config(), NOW)
        self.assertEqual(health["status"], "WARNING")
        self.assertIn("Backup filesystem usage 83.00%", health["text"])
        self.assertNotIn("CRITICAL", health["text"])

    def test_unknown_root_rejected(self):
        p = Path(self.tmp.name) / "policy.json"
        p.write_text(json.dumps({**self.config, "backup_root": "/"}))
        with self.assertRaises(c.Unsafe):
            c.read_config(p)

    def test_plan_key_detects_changed_selection(self):
        self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        plan = self.plan()
        changed = {**plan, "selected": []}
        self.assertNotEqual(c.plan_key(plan), c.plan_key(changed))

    def test_lock_busy_cli_refuses_execution(self):
        old = self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        with open(self.config["lock_file"], "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(c, "read_config", return_value=self.config), patch.object(
                    c.sys, "argv", ["cleanup", "--execute"]), patch.object(
                    c.sys, "stderr", io.StringIO()):
                self.assertEqual(c.main(), 1)
        self.assertEqual(len(list(old.iterdir())), 11)

    def test_reviewed_plan_mismatch_cli_refuses_execution(self):
        old = self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        plan = self.plan()
        reviewed = self.state / "reviewed.json"
        reviewed.write_text(json.dumps({**plan, "selected": []}))
        with patch.object(c, "read_config", return_value=self.config), patch.object(
                c, "build_plan", return_value=plan), patch.object(
                c.sys, "argv", ["cleanup", "--execute", "--apply-plan", str(reviewed)]), patch.object(
                c.sys, "stdout", io.StringIO()), patch.object(c.sys, "stderr", io.StringIO()):
            self.assertEqual(c.main(), 1)
        self.assertEqual(len(list(old.iterdir())), 11)

    def test_no_mode_is_dry_run(self):
        old = self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        plan = self.plan()
        with patch.object(c, "read_config", return_value=self.config), patch.object(
                c, "build_plan", return_value=plan), patch.object(
                c, "usage", return_value=plan["filesystem_before"]), patch.object(
                c.sys, "argv", ["cleanup"]), patch.object(c.sys, "stdout", io.StringIO()):
            self.assertEqual(c.main(), 0)
        self.assertTrue(old.exists()); self.assertFalse((self.state / "last-run.json").exists())

    def test_health_stale_and_failed_run_warns(self):
        self.snapshot(NOW)
        (self.state / "last-run.json").write_text(json.dumps({
            "timestamp": (NOW - timedelta(hours=40)).isoformat(), "mode": "execute",
            "root": str(self.root), "errors": ["verification failed"]}))
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value={"usage_percent": 30}):
            result = c.health(self.config, NOW)
        self.assertEqual(result["status"], "WARNING")
        self.assertIn("stale", result["text"])
        self.assertIn("Cleanup: Failed", result["text"])

    def test_disposable_kept_if_pressure_resolved(self):
        self.snapshot(NOW); p = self.disposable(); plan = self.plan(99)
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value={"usage_percent": 50}):
            deleted, reclaimed, errors = c.execute(self.config, plan, c.Log(self.state, NOW))
        self.assertEqual((deleted, reclaimed, errors), ([], 0, [])); self.assertTrue(p.exists())

    def test_explicit_manual_snapshot_pin_overrides_retention(self):
        old = self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        self.config["protected_snapshots"] = {old.name: "manual provenance uncertain"}
        self.assertEqual(self.plan()["selected"], [])

    def test_recent_verified_dry_run_reuses_only_unchanged_identities(self):
        old = self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        original = self.plan()
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value={"usage_percent": 50}), patch.object(
                c, "verify_snapshot", side_effect=AssertionError("Unexpected rehash")):
            revised = c.build_plan(self.config, NOW, verified_plan=original)
        self.assertEqual(c.plan_key(revised), c.plan_key(original))
        (old / "CONTENTS.txt").write_bytes(b"changed")
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value={"usage_percent": 50}):
            changed = c.build_plan(self.config, NOW, verified_plan=original)
        self.assertEqual(changed["selected"], []); self.assertTrue(changed["errors"])

    def test_stale_dry_run_cache_rejected(self):
        self.snapshot(NOW); original = self.plan()
        original["timestamp"] = (NOW - timedelta(hours=2)).isoformat()
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value={"usage_percent": 50}):
            with self.assertRaises(c.Unsafe):
                c.build_plan(self.config, NOW, verified_plan=original)

    def test_fifo_component_rejected_without_blocking(self):
        old = self.snapshot(NOW - timedelta(days=500)); self.snapshot(NOW)
        (old / "CONTENTS.txt").unlink()
        os.mkfifo(old / "CONTENTS.txt")
        plan = self.plan()
        self.assertEqual(plan["selected"], []); self.assertTrue(plan["errors"])

    def test_audited_coverage_gap_warns_even_below_pressure_threshold(self):
        self.snapshot(NOW)
        self.config["coverage_warnings"] = ["Service live state is outside the producer scope"]
        (self.state / "last-run.json").write_text(json.dumps({
            "timestamp": NOW.isoformat(), "mode": "execute", "root": str(self.root), "errors": []}))
        with patch.object(c, "check_mount", return_value=self.identity), patch.object(
                c, "usage", return_value={"usage_percent": 30}):
            result = c.health(self.config, NOW)
        self.assertEqual(result["status"], "WARNING")
        self.assertIn(self.config["coverage_warnings"][0], result["text"])

    def test_changed_service_mount_preserves_old_versions_last_backup(self):
        old = record(NOW - timedelta(days=500))
        new = record(NOW)
        old["bindings"] = {"app": "old-source"}
        new["bindings"] = {"app": "new-source"}
        reasons, _ = c.retention([old, new], NOW)
        self.assertTrue(reasons[old["name"]])
        self.assertTrue(any(r.startswith("last-mount-version:") for r in reasons[old["name"]]))

    def test_disposable_old_mount_cannot_be_replaced_by_new_mount(self):
        self.snapshot(NOW); p = self.disposable()
        marker = json.loads((p / c.MARKER).read_text())
        marker["bindings"]["app"] = "different-mount-version"
        (p / c.MARKER).write_text(json.dumps(marker))
        os.utime(p / c.MARKER, (NOW.timestamp() - 10 * 86400,) * 2)
        self.assertEqual(self.plan(99)["selected"], [])


if __name__ == "__main__":
    unittest.main()
