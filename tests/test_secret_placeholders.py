import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "check_secrets", Path(__file__).resolve().parents[1] / "scripts/check-secrets.py")
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


class PlaceholderTests(unittest.TestCase):
    def test_documented_placeholders(self):
        for value in ("CHANGE_ME", "'CHANGE_ME'", '"${TOKEN}"', "${TOKEN:-CHANGE_ME}",
                      "${TOKEN-CHANGE_ME}", "${TOKEN:-}", "${TOKEN:?Set TOKEN}",
                      "${TOKEN?Set TOKEN}", "null", "~", "", "''"):
            with self.subTest(value=value):
                self.assertTrue(scanner.is_safe_placeholder(value))

    def test_embedded_markers_and_literal_defaults_are_not_safe(self):
        for value in ("exampleCHANGE_MEvalue", "CHANGE_ME-suffix", "${TOKEN}suffix",
                      "${TOKEN:-example-literal}", "${TOKEN", "${}", "${1TOKEN}",
                      "'CHANGE_ME", '"CHANGE_ME\'', "${TOKEN}\nextra"):
            with self.subTest(value=value):
                self.assertFalse(scanner.is_safe_placeholder(value))

    def test_sensitive_assignment_values_use_strict_validation(self):
        for line in ("PASSWORD: prefixCHANGE_MEsuffix", "- TOKEN=${TOKEN}suffix",
                     "SECRET=${SECRET:-example-literal}"):
            match = scanner.SENSITIVE_ASSIGNMENT.match(line)
            self.assertIsNotNone(match)
            self.assertFalse(scanner.is_safe_placeholder(match[1]))
