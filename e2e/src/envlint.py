#!/usr/bin/env python3
"""Validate .env files from a path or stdin."""

import argparse
import json
import re
import sys


KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def make_issue(line, level, code, message):
    """Create a normalized issue dictionary."""
    return {"line": line, "level": level, "code": code, "message": message}


def strip_export(line):
    """Remove a leading export prefix from a non-comment line."""
    if line.startswith("export "):
        return line[7:]
    return line


def parse_line(line, line_number):
    """Parse one .env line into a record used by checks."""
    text = line.rstrip("\n\r")
    stripped = text.strip()
    record = {
        "line": line_number,
        "raw": text,
        "ignored": False,
        "valid": False,
        "key": None,
        "value": None,
    }

    if not stripped or stripped.startswith("#"):
        record["ignored"] = True
        return record

    candidate = strip_export(text)
    if "=" not in candidate:
        return record

    key, value = candidate.split("=", 1)
    if not KEY_RE.match(key):
        return record

    record["valid"] = True
    record["key"] = key
    record["value"] = value
    return record


def parse_env(text):
    """Parse .env text into line records."""
    return [parse_line(line, index) for index, line in enumerate(text.splitlines(), 1)]


def check_format(records):
    """Return errors for non-blank, non-comment lines that are not KEY=VALUE."""
    issues = []
    for record in records:
        if not record["ignored"] and not record["valid"]:
            issues.append(
                make_issue(
                    record["line"],
                    "error",
                    "invalid_format",
                    "invalid format",
                )
            )
    return issues


def check_duplicates(records):
    """Return errors for keys that appear more than once."""
    seen = {}
    for record in records:
        if record["valid"]:
            seen.setdefault(record["key"], []).append(record["line"])

    issues = []
    for key in sorted(seen):
        lines = seen[key]
        if len(lines) > 1:
            line_text = ", ".join(str(line) for line in lines)
            issues.append(
                make_issue(
                    lines[0],
                    "error",
                    "duplicate_key",
                    "%s is duplicated on lines %s" % (key, line_text),
                )
            )
    return issues


def check_empty(records, strict=False):
    """Return warnings, or errors in strict mode, for empty values."""
    level = "error" if strict else "warning"
    issues = []
    for record in records:
        if record["valid"] and record["value"] == "":
            issues.append(
                make_issue(
                    record["line"],
                    level,
                    "empty_value",
                    "%s has empty value" % record["key"],
                )
            )
    return issues


def check_schema(records, required_keys):
    """Return errors for required keys missing from valid env assignments."""
    present = set()
    for record in records:
        if record["valid"]:
            present.add(record["key"])

    issues = []
    for key in sorted(required_keys):
        if key not in present:
            issues.append(
                make_issue(
                    0,
                    "error",
                    "missing_required",
                    "%s is required but missing" % key,
                )
            )
    return issues


def parse_schema(text):
    """Parse required key names from schema text."""
    keys = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        keys.append(stripped)
    return keys


def lint_text(text, required_keys=None, strict=False):
    """Run all enabled checks against .env text."""
    records = parse_env(text)
    issues = []
    issues.extend(check_format(records))
    issues.extend(check_duplicates(records))
    issues.extend(check_empty(records, strict=strict))
    if required_keys is not None:
        issues.extend(check_schema(records, required_keys))
    issues.sort(key=lambda issue: (issue["line"], issue["code"], issue["message"]))
    return issues


def read_text(path):
    """Read UTF-8 text from a file path."""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def read_input(path):
    """Read UTF-8 text from a path or stdin when path is '-'."""
    if path == "-":
        return sys.stdin.read()
    return read_text(path)


def has_problem(issues, strict=False):
    """Return True when issues should produce exit code 1."""
    for issue in issues:
        if issue["level"] == "error" or (strict and issue["level"] == "warning"):
            return True
    return False


def print_text_issues(issues):
    """Print human-readable issues or ok."""
    if not issues:
        print("ok")
        return
    for issue in issues:
        print(
            "line %s: %s [%s] %s"
            % (issue["line"], issue["level"], issue["code"], issue["message"])
        )


def build_parser():
    """Build the command line argument parser."""
    parser = argparse.ArgumentParser(description="Validate .env files.")
    parser.add_argument("file", help=".env file path, or '-' for stdin")
    parser.add_argument("--schema", help="file listing required KEY names")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--json", action="store_true", help="output JSON")
    return parser


def main(argv=None):
    """Run the envlint CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        text = read_input(args.file)
        required_keys = None
        if args.schema:
            required_keys = parse_schema(read_text(args.schema))
    except OSError as exc:
        print("usage error: %s" % exc, file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        print("usage error: %s" % exc, file=sys.stderr)
        return 2

    issues = lint_text(text, required_keys=required_keys, strict=args.strict)
    problem = has_problem(issues, strict=args.strict)

    if args.json:
        print(json.dumps({"issues": issues, "ok": not problem}, sort_keys=True))
    else:
        print_text_issues(issues)

    return 1 if problem else 0


if __name__ == "__main__":
    sys.exit(main())
