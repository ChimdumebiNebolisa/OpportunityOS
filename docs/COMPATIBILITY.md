# Compatibility record

Recorded 2026-08-21.

| Component | Status | Evidence |
| --- | --- | --- |
| Windows 11 host | PASS | Local unit, integration, E2E, migration, CLI, package, and audit checks. |
| Python 3.12.10 | PASS | Locked environment and test run. Package declares Python ≥3.11. |
| SQLite/SQLAlchemy/Alembic | PASS | Fresh migration, FK/WAL/integrity, backup/restore tests. |
| MCP Python SDK 1.29.0 | PASS | Server import and tool/skill contract tests. |
| Hermes native Windows | GATED | Not installed in this workspace; commands checked against current upstream docs. |
| Hermes OpenAI Codex OAuth | GATED | Requires interactive user device login. No credentials inspected. |
| Discord gateway | GATED | Requires user-owned bot, token, allowlist, and private DM test. |
| Optional GitHub authentication | GATED | Public mocked adapter covered; private credential not supplied. |
| macOS/Linux | CI-CONTRACT | Cross-platform paths and POSIX setup script implemented; no live host evidence here. |

`GATED` means exact manual verification remains; it does not mean PASS. Update this file after every
live compatibility run with date, versions, and observed result.
