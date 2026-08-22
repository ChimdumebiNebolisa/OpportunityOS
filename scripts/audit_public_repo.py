"""Fail when the checkout contains obvious private artifacts or secrets."""

from __future__ import annotations

import json
import re
from pathlib import Path

IGNORED_DIRECTORIES = {".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist"}
PRIVATE_NAMES = {"profile.yaml", "policy.yaml", "strategy.yaml", "state.db"}
SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[^\s'\"]{12,}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings: list[dict[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        if path.name in PRIVATE_NAMES or path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            findings.append(
                {"path": str(path.relative_to(root)), "reason": "private runtime artifact"}
            )
            continue
        if path.suffix.lower() in {".py", ".yaml", ".yml", ".json", ".md", ".txt"}:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if SECRET_PATTERN.search(text):
                findings.append({"path": str(path.relative_to(root)), "reason": "possible secret"})
    print(
        json.dumps({"result": "PASS" if not findings else "FAIL", "findings": findings}, indent=2)
    )
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
