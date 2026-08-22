"""Private runtime paths and small YAML document helpers."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from platformdirs import PlatformDirs


class RuntimeStateError(RuntimeError):
    """Raised when private runtime state is unsafe or invalid."""


def _reject_reparse_traversal(path: Path) -> None:
    current = Path(path.absolute().anchor)
    for part in path.absolute().parts[1:]:
        current /= part
        is_junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or bool(is_junction()):
            raise RuntimeStateError("Private runtime paths cannot traverse symlinks or junctions")


def _outside_repository(path: Path, repository: Path) -> None:
    resolved = path.resolve(strict=False)
    if resolved == repository or resolved.is_relative_to(repository):
        raise RuntimeStateError("Private runtime state cannot be stored inside the repository")


@dataclass(frozen=True)
class RuntimePaths:
    """The four private documents and database used by one installation."""

    root: Path
    repository: Path

    @classmethod
    def from_environment(cls, repository: Path | None = None) -> RuntimePaths:
        repository_root = (repository or Path.cwd()).resolve()
        dirs = PlatformDirs("OpportunityOS", "OpportunityOS", roaming=False)
        configured = os.environ.get("OPPORTUNITYOS_DATA_DIR")
        root = Path(configured) if configured else Path(dirs.user_data_dir)
        root = root.absolute()
        _reject_reparse_traversal(root)
        _outside_repository(root, repository_root)
        return cls(root=root.resolve(strict=False), repository=repository_root)

    @property
    def profile(self) -> Path:
        return self.root / "profile.yaml"

    @property
    def policy(self) -> Path:
        return self.root / "policy.yaml"

    @property
    def strategy(self) -> Path:
        return self.root / "strategy.yaml"

    @property
    def database(self) -> Path:
        return self.root / "state.db"

    @property
    def export_directory(self) -> Path:
        return self.root / "exports"

    def ensure_root(self) -> None:
        _reject_reparse_traversal(self.root)
        _outside_repository(self.root, self.repository)
        self.root.mkdir(parents=True, exist_ok=True)
        self.export_directory.mkdir(exist_ok=True)

    def ensure_initialized(self) -> None:
        self.ensure_root()
        documents = {
            self.profile: {
                "version": 1,
                "identity": {"display_name": None},
                "education": {},
                "work": {},
                "location": {},
                "authorization": {},
                "interests": [],
                "goals": [],
                "skills": [],
                "experience": [],
                "preferences": {},
                "custom": {},
            },
            self.policy: {
                "version": 1,
                "global": {
                    "require_official_verification": True,
                    "reject_closed": True,
                    "reject_expired": True,
                },
                "categories": {},
            },
            self.strategy: {
                "version": 1,
                "global": {
                    "verification": {
                        "prefer_primary_sources": True,
                        "aggregators_are_leads_only": True,
                    }
                },
                "categories": {},
            },
        }
        for path, value in documents.items():
            if not path.exists():
                write_yaml(path, value)


def read_yaml(path: Path, *, expected_mapping: bool = True) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise RuntimeStateError(f"Could not read {path.name}: {error}") from error
    if expected_mapping and not isinstance(value, dict):
        raise RuntimeStateError(f"{path.name} must contain a YAML mapping")
    return value if isinstance(value, dict) else {}


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(value, sort_keys=False, allow_unicode=False)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary, path)
        with suppress(OSError):
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
