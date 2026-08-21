# Compatibility record

Recorded 2026-08-21.

| Component | Status | Evidence |
| --- | --- | --- |
| Windows 11 host | PASS | Local unit, integration, E2E, migration, CLI, package, and audit checks. |
| Python 3.12.10 | PASS | Locked environment and test run. Package declares Python ≥3.11. |
| SQLite/SQLAlchemy/Alembic | PASS | Fresh migration, FK/WAL/integrity, backup/restore tests. |
| MCP Python SDK 1.29.0 | PASS | Server import and tool/skill contract tests. |
| Hermes native Windows | PASS | Hermes Agent v0.20.5 (2026.8.19), upstream 23a64a97, installed by the native git installer under the documented `%LOCALAPPDATA%` layout. The installer-managed bin directory is present in User PATH; fallback discovery also works in an older shell. |
| Hermes OpenAI Codex OAuth | PASS | `hermes auth status openai-codex` reported logged in. No credential file or value was inspected. |
| OpportunityOS MCP configuration | PASS | `hermes mcp list` reported `opportunityos` enabled. A controlled text round trip invoked the typed `system_status` MCP tool. |
| Discord configuration and gateway | PASS | User-owned bot, numeric allowlist, private server channel, and running gateway were configured. `hermes gateway list` reported the current gateway PID. |
| Live Hermes/Codex/MCP/Discord round trip | PASS | On 2026-08-21 an authorized text message reached Hermes, used OpenAI Codex, invoked OpportunityOS `system_status`, and returned to Discord. This does not cover screenshot, PDF, or unauthorized-user acceptance cases. |
| Optional GitHub authentication | GATED | Public mocked adapter covered; private credential not supplied. |
| macOS/Linux | CI-CONTRACT | Cross-platform paths and POSIX setup script implemented; no live host evidence here. |

`GATED` means exact manual verification remains; it does not mean PASS. Update this file after every
live compatibility run with date, versions, and observed result.
