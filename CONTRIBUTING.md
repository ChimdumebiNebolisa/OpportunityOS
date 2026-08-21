# Contributing

Use Python 3.11 or newer and install the locked development environment:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install uv
.venv\Scripts\uv sync --all-extras --frozen
```

Keep changes small, preserve the application/domain/adapter boundaries in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and add tests for behavior changes. Never add real
personal data or credentials; fixtures must be visibly synthetic.

Run before opening a pull request:

```powershell
.venv\Scripts\uv lock --check
.venv\Scripts\uv run ruff format --check .
.venv\Scripts\uv run ruff check .
.venv\Scripts\uv run mypy src
.venv\Scripts\uv run pytest --cov=opportunityos --cov-fail-under=80
.venv\Scripts\uv run python scripts/audit_public_repo.py
.venv\Scripts\uv build
```

Schema changes require an Alembic migration and migration test. Decision-rule changes require a
new ruleset version and replay tests. External actions remain prohibited.
