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

## V3 discovery activation record

Recorded 2026-08-22. The existing five category scout jobs remain reversible and are paused while
the two global jobs are enabled:

| Component | Status | Evidence |
| --- | --- | --- |
| V3 MCP discovery interface | PASS | `hermes mcp test opportunityos` connected and discovered 68 tools, including begin/query/expand/source-check/finish/coverage/strategy/source/status. |
| V3 public defaults | PASS | `opportunityos discovery status` reports 17-lens configuration and 06:00/18:00 schedules; settings, migration, and focused discovery tests pass. |
| Global morning schedule | PASS | Hermes job `26498abdfd3a`, `0 6 * * *`, active, next run 2026-08-22 06:00 America/Chicago. |
| Global evening schedule | PASS | Hermes job `73081ca4517c`, `0 18 * * *`, active, next run 2026-08-22 18:00 America/Chicago. |
| Legacy category schedules | PAUSED | `524cd2c42dac`, `b995d9173f16`, `59570c67ac3c`, `f77c6d8c3073`, and `ec6db71873e8`; resume these IDs to roll back activation. |
| Pre-v3 private backup | PASS | Verified private backup created before implementation; see the private backup directory. |
| Post-v3 private backup | PASS | Verified private backup created 2026-08-22T03:27:46Z with SQLite integrity `ok`. |
| Three consecutive live global cycles | GATED | Not claimed in this implementation session; scheduled live evidence must accumulate without fabricating search or Discord results. |
| Current discovery health | GATED | No live V3 cycle has completed yet, so health honestly reports `stale_or_incomplete`. |
| Package build | GATED | Local venv lacks `hatchling`, and `uv` is unavailable; no build result is claimed. |
