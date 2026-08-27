#!/usr/bin/env python3
"""Fail closed when forbidden files or likely live secrets are present."""

from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_NAMES = [
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"(^|/)secrets\.ya?ml$", re.I),
    re.compile(r"(^|/)wg0\.conf$", re.I),
    re.compile(r"\.(db|sqlite3?|pem|key|p12|pfx)$", re.I),
    re.compile(r"(^|/)config\.xml$", re.I),
]

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bprivatekey\s*=\s*\S+"),
    re.compile(r"(?i)<ApiKey>[^<]{8,}</ApiKey>"),
]

SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)^\s*(?:-\s*)?(?:POSTGRES_PASSWORD|DB_PASSWORD|PASSWORD|PASSWD|API_KEY|"
    r"APIKEY|TOKEN|SECRET|PRIVATE_KEY|WIREGUARD_PRIVATE_KEY)\s*[:=]\s*(.+?)\s*$"
)


def is_safe_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'")
    return (
        "CHANGE_ME" in normalized
        or normalized.startswith("${")
        or normalized in {"", "null", "~"}
    )


def files_to_scan() -> list[Path]:
    try:
        output = subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            text=True,
        )
        return [ROOT / line for line in output.splitlines() if line]
    except subprocess.CalledProcessError:
        return [
            p
            for p in ROOT.rglob("*")
            if p.is_file()
            and ".git" not in p.parts
            and "__pycache__" not in p.parts
            and p.suffix != ".pyc"
        ]


def main() -> int:
    failures: list[str] = []
    private_literals = {Path.home().name, socket.gethostname()}
    try:
        private_literals.update(subprocess.check_output(["hostname", "-I"], text=True).split())
    except (OSError, subprocess.CalledProcessError):
        pass
    private_literals.discard("")

    for path in files_to_scan():
        rel = path.relative_to(ROOT).as_posix()
        if any(pattern.search(rel) for pattern in FORBIDDEN_NAMES):
            if rel != ".env.example":
                failures.append(f"forbidden filename: {rel}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(literal in text for literal in private_literals):
            failures.append(f"host-specific identifier in: {rel}")
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"secret-like content in: {rel}")
                break
        else:
            for line_number, line in enumerate(text.splitlines(), start=1):
                match = SENSITIVE_ASSIGNMENT.match(line)
                if match and not is_safe_placeholder(match.group(1)):
                    failures.append(
                        f"literal sensitive assignment in: {rel}:{line_number}"
                    )
                    break

    if failures:
        print("Secret scan FAILED:")
        print("\n".join(f"- {item}" for item in failures))
        return 1
    print("Secret scan passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
