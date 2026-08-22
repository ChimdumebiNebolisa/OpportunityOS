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
| Package build | PASS | `.venv\\Scripts\\python.exe -m build` produced the source distribution and wheel. |

## V3.1 personal-intelligence activation record

Recorded 2026-08-22. The V3.1 schedule is active and remains reversible; source capabilities are
reported independently and unsupported providers are not represented as synchronized:

| Component | Status | Evidence |
| --- | --- | --- |
| V3.1 MCP personal-intelligence interface | PASS | `hermes mcp test opportunityos` connected and discovered 77 typed tools, including personal run, source, and reconciliation operations. |
| V3.1 local skill | PASS | Hermes reports 7 enabled local skills, including `opportunityos-profile-intelligence`; `SKILL.md` and its agent metadata are installed under the private Hermes skill root. |
| Personal-intelligence defaults and migration | PASS | 05:00 `America/Chicago` defaults load; migration and focused V3.1 tests pass. |
| Personal-intelligence schedule | PASS | Hermes job `4748a197c6ca`, `0 5 * * *`, active, Discord delivery, repository workdir. |
| GitHub source capability | GATED | No `OPPORTUNITYOS_GITHUB_USERNAME` is configured; runtime reports unavailable without claiming synchronization. |
| Gmail source capability | GATED | No supported Gmail provider is configured; runtime reports `gmail_provider_unavailable`. |
| ChatGPT continuous capability | GATED | No supported continuous provider is configured; snapshot-only mode remains available as an explicit control. |
| V3.1 private backup | PASS | Verified final backup created 2026-08-22T05:26:02Z with SQLite integrity `ok`; private path intentionally omitted. |
| Local blocked-capability smoke sweep | PASS | `opportunityos profile intelligence run` completed with an honest `partial`/`silent` result, zero records inspected, and explicit blocked details for all three unconfigured sources. |
| First live personal-intelligence cycle | GATED | Schedule is installed but no live source cycle is claimed in this implementation session. |
