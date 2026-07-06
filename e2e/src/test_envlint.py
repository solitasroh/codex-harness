"""Tests for envlint."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import envlint


ROOT = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(ROOT, "envlint.py")


class EnvLintFunctionTests(unittest.TestCase):
    """Unit tests for parser and check behavior."""

    def test_clean_file(self):
        issues = envlint.lint_text("API_KEY=abc\nPORT=8080\n")
        self.assertEqual([], issues)

    def test_missing_equals_format_error(self):
        issues = envlint.lint_text("API_KEY\n")
        self.assertEqual("invalid_format", issues[0]["code"])
        self.assertEqual("error", issues[0]["level"])
        self.assertEqual(1, issues[0]["line"])

    def test_duplicate_key(self):
        issues = envlint.lint_text("A=1\nB=2\nA=3\n")
        self.assertEqual(1, len(issues))
        self.assertEqual("duplicate_key", issues[0]["code"])
        self.assertIn("lines 1, 3", issues[0]["message"])

    def test_empty_value_warning_default(self):
        issues = envlint.lint_text("EMPTY=\n")
        self.assertEqual("warning", issues[0]["level"])
        self.assertFalse(envlint.has_problem(issues))

    def test_empty_value_error_strict(self):
        issues = envlint.lint_text("EMPTY=\n", strict=True)
        self.assertEqual("error", issues[0]["level"])
        self.assertTrue(envlint.has_problem(issues, strict=True))

    def test_schema_missing_key(self):
        issues = envlint.lint_text("A=1\n", required_keys=["A", "B"])
        self.assertEqual(1, len(issues))
        self.assertEqual("missing_required", issues[0]["code"])
        self.assertIn("B", issues[0]["message"])

    def test_export_prefix(self):
        issues = envlint.lint_text("export TOKEN=abc\n")
        self.assertEqual([], issues)
        record = envlint.parse_env("export TOKEN=abc\n")[0]
        self.assertEqual("TOKEN", record["key"])

    def test_quoted_value(self):
        issues = envlint.lint_text('NAME="a b"\nOTHER=\'c d\'\n')
        self.assertEqual([], issues)

    def test_blank_and_comment_ignored(self):
        issues = envlint.lint_text("\n# comment\nA=1\n")
        self.assertEqual([], issues)

    def test_empty_file_is_ok(self):
        issues = envlint.lint_text("")
        self.assertEqual([], issues)


class EnvLintCliTests(unittest.TestCase):
    """CLI tests for IO, JSON, and exit codes."""

    def run_cli(self, args, input_text=None):
        return subprocess.run(
            [sys.executable, CLI] + args,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_stdin_input(self):
        result = self.run_cli(["-"], input_text="A=1\n")
        self.assertEqual(0, result.returncode)
        self.assertEqual("ok\n", result.stdout)

    def test_json_output(self):
        result = self.run_cli(["--json", "-"], input_text="A\n")
        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual("invalid_format", payload["issues"][0]["code"])

    def test_schema_file_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            schema_path = os.path.join(tmpdir, "schema")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write("A=1\n")
            with open(schema_path, "w", encoding="utf-8") as handle:
                handle.write("# required\nA\nB\n")

            result = self.run_cli(["--schema", schema_path, env_path])

        self.assertEqual(1, result.returncode)
        self.assertIn("missing_required", result.stdout)


if __name__ == "__main__":
    unittest.main()
