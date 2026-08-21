"""Public-repository privacy and secret audit."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditFinding:
    path: str
    rule: str


PROHIBITED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}
PROHIBITED_NAMES = {".env", "auth.json", "credentials.json"}
PROHIBITED_SIDECARS = (
    ".db-wal",
    ".db-shm",
    ".sqlite-wal",
    ".sqlite-shm",
    ".sqlite3-wal",
    ".sqlite3-shm",
)
SECRET_PATTERNS = {
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "discord_token_assignment": re.compile(r"DISCORD_BOT_TOKEN\s*=\s*[^\s<>{}$]+"),
    "windows_user_path": re.compile(r"[A-Za-z]:\\Users\\[^%\\\s]+\\"),
}


def audit_public_repository(root: Path) -> list[AuditFinding]:
    repository = root.resolve()
    findings: list[AuditFinding] = []
    ignored_dirs = {
        ".git",
        ".venv",
        ".playwright-cli",
        ".hypothesis",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        "htmlcov",
        "output",
    }
    ignored_files = {".coverage", "coverage.xml"}
    for path in repository.rglob("*"):
        if any(part in ignored_dirs for part in path.relative_to(repository).parts):
            continue
        if path.name in ignored_files:
            continue
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(repository).as_posix()
        name = path.name.lower()
        if (
            name in PROHIBITED_NAMES
            or (name.startswith(".env.") and name != ".env.example")
            or path.suffix.lower() in PROHIBITED_SUFFIXES
            or name.endswith(PROHIBITED_SIDECARS)
        ):
            findings.append(AuditFinding(relative, "prohibited_private_artifact"))
            continue
        if path.stat().st_size > 5_000_000:
            findings.append(AuditFinding(relative, "unexpected_large_file"))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for rule, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(AuditFinding(relative, rule))
    return findings
