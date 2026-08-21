"""Small shared primitives."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


def require_uuid(value: str) -> str:
    return str(UUID(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
