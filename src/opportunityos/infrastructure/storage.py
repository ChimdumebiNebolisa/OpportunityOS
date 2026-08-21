"""Private storage with containment and symlink protections."""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from opportunityos.config.settings import Settings
from opportunityos.util import new_id, sha256_bytes


class UnsafePathError(ValueError):
    """Raised when a path escapes the approved private boundary."""


def is_reparse_point(path: Path) -> bool:
    """Return true for symlinks and Windows junctions without requiring Python 3.12."""
    is_junction = getattr(path, "is_junction", lambda: False)
    return path.is_symlink() or bool(is_junction())


def reject_reparse_traversal(path: Path) -> None:
    current = Path(path.absolute().anchor)
    for part in path.absolute().parts[1:]:
        current /= part
        if is_reparse_point(current):
            raise UnsafePathError("Private path cannot traverse a symlink or junction")


class PrivateStorage:
    ALLOWED_CATEGORIES: ClassVar[set[str]] = {
        "attachments",
        "sources",
        "applications",
        "backups",
        "logs",
        "exports",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.configured_root = settings.data_dir.absolute()
        reject_reparse_traversal(self.configured_root)
        self.root = self.configured_root.resolve(strict=False)
        self._validate_root()

    def _validate_root(self) -> None:
        repo = self.settings.repository_root.resolve(strict=False)
        if self.root == repo or self.root.is_relative_to(repo):
            raise UnsafePathError("Private data directory cannot be inside the repository")
        reject_reparse_traversal(self.configured_root)

    def initialize(self) -> None:
        self._validate_root()
        self.root.mkdir(parents=True, exist_ok=True)
        for category in self.ALLOWED_CATEGORIES:
            (self.root / category).mkdir(exist_ok=True)

    def require_private(self, path: Path) -> Path:
        reject_reparse_traversal(path)
        candidate = path.resolve(strict=False)
        if candidate == self.root or candidate.is_relative_to(self.root):
            return candidate
        raise UnsafePathError("Path is outside the approved private root")

    def category_path(self, category: str) -> Path:
        if category not in self.ALLOWED_CATEGORIES:
            raise UnsafePathError("Unsupported private storage category")
        return self.require_private(self.root / category)

    def store_bytes(self, category: str, value: bytes, suffix: str = ".bin") -> tuple[Path, str]:
        self.initialize()
        safe_suffix = (
            suffix.lower() if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix.lower()) else ".bin"
        )
        destination = self.require_private(
            self.category_path(category) / f"{new_id()}{safe_suffix}"
        )
        destination.write_bytes(value)
        return destination, sha256_bytes(value)

    @property
    def database_path(self) -> Path:
        self.initialize()
        return self.require_private(self.root / "opportunityos.sqlite3")
