import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "atomic_json", Path(__file__).resolve().parents[1] / "automation/atomic_json.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class AtomicJsonTests(unittest.TestCase):
    def test_complete_private_snapshot_replaces_old_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"old": true}')
            module.write_json(path, {"new": "δοκιμή"}, indent=2)
            self.assertEqual(json.loads(path.read_text()), {"new": "δοκιμή"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_failed_serialization_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"old": true}')
            with self.assertRaises(TypeError):
                module.write_json(path, {"bad": object()})
            self.assertEqual(path.read_text(), '{"old": true}')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_sync_and_replace_failures_preserve_original(self):
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "state.json"
                path.write_text('{"old": true}')
                with patch.object(module.os, operation, side_effect=OSError("synthetic failure")), \
                        self.assertRaises(OSError):
                    module.write_json(path, {"new": True})
                self.assertEqual(path.read_text(), '{"old": true}')
                self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_readers_keep_old_complete_file_until_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"old": true}')
            original = module.os.replace

            def checked_replace(source, destination):
                self.assertEqual(Path(source).parent, path.parent)
                self.assertEqual(json.loads(path.read_text()), {"old": True})
                self.assertEqual(json.loads(Path(source).read_text()), {"new": True})
                original(source, destination)

            with patch.object(module.os, "replace", side_effect=checked_replace):
                module.write_json(path, {"new": True})

    def test_first_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            module.write_json(path, {})
            self.assertEqual(json.loads(path.read_text()), {})
