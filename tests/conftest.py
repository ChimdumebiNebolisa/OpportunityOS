from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from opportunityos.application.context import ApplicationContext


@pytest.fixture
def context_factory(tmp_path: Path) -> Callable[[], ApplicationContext]:
    counter = 0

    def create() -> ApplicationContext:
        nonlocal counter
        counter += 1
        root = tmp_path / f"case-{counter}"
        repository = root / "repository"
        repository.mkdir(parents=True)
        (repository / ".gitignore").write_text("*.sqlite3\n", encoding="utf-8")
        return ApplicationContext.create(
            repository,
            data_dir=root / "private-data",
            config_dir=root / "private-config",
        )

    return create
