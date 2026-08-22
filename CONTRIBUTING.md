# Contributing

Use Python 3.11 or newer and install the locked development environment:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install uv
.venv\Scripts\uv sync --all-extras --frozen
```

Keep changes focused on Profile, Policy, Strategy, or History. Add synthetic tests for behavior
changes and never commit private runtime state or credentials.

Run before opening a pull request:

```powershell
.venv\Scripts\uv lock --check
.venv\Scripts\uv run ruff check .
.venv\Scripts\uv run mypy src
.venv\Scripts\uv run pytest --cov=opportunityos --cov-fail-under=80
.venv\Scripts\uv run python scripts/audit_public_repo.py
.venv\Scripts\uv build
```
