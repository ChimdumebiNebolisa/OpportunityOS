"""Safe, versioned ZIP portability for private OpportunityOS state."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .runtime import RuntimePaths, RuntimeStateError, read_yaml
from .store import SCHEMA_VERSION, HistoryStore

EXPORT_VERSION = 1
EXPORT_FILES = ("manifest.json", "profile.yaml", "policy.yaml", "strategy.yaml", "state.db")
MAX_IMPORT_BYTES = 100 * 1024 * 1024


def export_state(paths: RuntimePaths, destination: Path) -> dict[str, Any]:
    HistoryStore(paths).initialize()
    destination = destination.absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "export_version": EXPORT_VERSION,
        "state_schema_version": SCHEMA_VERSION,
        "files": list(EXPORT_FILES[1:]),
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
            for name, path in (
                ("profile.yaml", paths.profile),
                ("policy.yaml", paths.policy),
                ("strategy.yaml", paths.strategy),
                ("state.db", paths.database),
            ):
                archive.write(path, name)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"schema_version": 1, "export_path": str(destination), "files": list(EXPORT_FILES[1:])}


def _validate_member(name: str) -> None:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or name not in EXPORT_FILES:
        raise RuntimeStateError(f"Unsafe or unsupported export member: {name}")


def _validate_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise RuntimeStateError(f"Unsupported imported database version: {version}")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        required = {"opportunities", "runs", "discoveries", "feedback", "strategy_revisions"}
        if not required.issubset(tables):
            raise RuntimeStateError("Imported database is missing required history tables")
    finally:
        connection.close()


def import_state(paths: RuntimePaths, source: Path) -> dict[str, Any]:
    paths.ensure_root()
    source = source.absolute()
    if not source.is_file():
        raise RuntimeStateError("Export archive does not exist")
    staging = Path(tempfile.mkdtemp(prefix="opportunityos-import-", dir=paths.root))
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if (
                len(members) != len(EXPORT_FILES)
                or sum(item.file_size for item in members) > MAX_IMPORT_BYTES
            ):
                raise RuntimeStateError("Export archive is too large or has an invalid file count")
            for item in members:
                _validate_member(item.filename)
            if {item.filename for item in members} != set(EXPORT_FILES):
                raise RuntimeStateError("Export archive is missing required files")
            manifest = json.loads(archive.read("manifest.json"))
            if (
                manifest.get("export_version") != EXPORT_VERSION
                or manifest.get("state_schema_version") != SCHEMA_VERSION
            ):
                raise RuntimeStateError("Incompatible export version")
            for name in EXPORT_FILES[1:]:
                target = staging / name
                target.write_bytes(archive.read(name))
        for name in ("profile.yaml", "policy.yaml", "strategy.yaml"):
            value = read_yaml(staging / name)
            if not isinstance(value, dict):
                raise RuntimeStateError(f"Imported {name} is invalid")
        _validate_database(staging / "state.db")
        for name in EXPORT_FILES[1:]:
            os.replace(staging / name, paths.root / name)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise RuntimeStateError(f"Could not import export safely: {error}") from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {
        "schema_version": 1,
        "imported": True,
        "source": str(source),
        "files": list(EXPORT_FILES[1:]),
    }
