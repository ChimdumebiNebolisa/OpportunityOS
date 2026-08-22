## 1. Durable configuration and schema

- [x] 1.1 Extend typed settings and safe public defaults for scout activation/schedules/catch-up, auto-preparation, execution, notifications, briefs, follow-up, backup retention, health, and automation controls; verify existing settings/private-path tests still pass.
- [x] 1.2 Add SQLAlchemy rows and indexes for reminder state, preparation-policy decisions, follow-up state, health state, brief runs, strategy snapshots, and persisted automation controls; verify `Base.metadata.tables` contains only the intended V2 tables.
- [x] 1.3 Add the forward Alembic migration with foreign keys, uniqueness constraints, UTC timestamps, bounded JSON fields, and downgrade support; verify upgrade/downgrade from an empty SQLite database.
- [x] 1.4 Add migration coverage from a V1-shaped database containing profile, opportunity, evaluation, action, application, scout, and audit records; verify all original records remain readable after V2 migration and the pre-migration backup is private and integrity-checked.

## 2. Deterministic behavioral policies

- [x] 2.1 Implement pure versioned policy functions for execution priority, completion leverage, reminder severity/materiality, notification ranking, follow-up dates, brief materiality, preparation gates, and preference sample sufficiency; verify boundary cases with focused unit tests.
- [x] 2.2 Extend the existing queue/next-action behavior through the execution interface so current evaluation/version/dependency guards remain authoritative and nearly complete urgent work can outrank distant higher-score work; verify existing queue tests plus V2 priority tests.
- [x] 2.3 Implement reminder state creation, escalation, duplicate fingerprints, daily cap/quiet-hour filtering, snooze, stop, pass, and explicit-applied transitions; verify ready/in-progress gates, cap ordering, and idempotent controls through application tests.
- [x] 2.4 Implement deterministic automatic-preparation gate evaluation and policy recording, then a rechecking execution path that calls the existing grounded packet compiler; verify positive and negative gates, stale state, budget exhaustion, private artifacts, and `external_submission_performed == false`.
- [x] 2.5 Implement explicit-submission follow-up timing, prohibition handling, due-state transitions, private grounded draft preparation, and completion marking; verify due/not-due/prohibited cases and that no outbound operation exists.
- [x] 2.6 Implement material daily/evening/weekly brief selection, silent results, bounded item counts, and evidence-bounded strategy snapshots; verify quiet-day silence, prioritization, sample-size limits, and no automatic policy mutation.
- [x] 2.7 Implement bounded profile/opportunity dependent reevaluation and material-change reporting through the existing decision interfaces; verify stale invalidation, reevaluation budget, decision-change surfacing, cosmetic-source silence, and unchanged unrelated opportunities.

## 3. Operations and automation integration

- [x] 3.1 Extend scout state handling for supported V2 categories, configurable schedules, catch-up windows, persisted controls, and material delivery without changing the existing usage-budget contract; verify quiet, duplicate, and catch-up scenarios.
- [x] 3.2 Implement automatic backup due/retention/status behavior by reusing the existing verified SQLite backup path; verify changed-database/weekly triggers, checksum/integrity manifests, retention bounds, and honest failure state.
- [x] 3.3 Implement health checks and recovery state for database integrity, scout freshness/errors, backup freshness, schedule presence, and safe Hermes observability; verify actionable failure, deduplication, recovery, and credential-value non-disclosure.
- [x] 3.4 Add least-privilege typed MCP tools for execution, reminders, auto-preparation, follow-up, briefs, propagation, health, automatic backup, and local controls; verify every tool is schema-valid, callable through the application interface, idempotent where required, and no tool can send/submit/upload/purchase/accept/withdraw.
- [x] 3.5 Add matching CLI commands for status/history, automation controls, manual bounded runs, next action, snooze/stop/pass, auto-preparation gate/execute, follow-up, briefs, health, and backup status; verify help output and end-to-end command behavior with private temporary runtime fixtures.
- [x] 3.6 Extend existing Hermes skills and add only necessary behavioral skills with fresh-session, budget, state-loading, redaction, and `[SILENT]` rules; verify skill references resolve to MCP tools and metadata contains no placeholders.
- [x] 3.7 Document configured schedules, Hermes cron inspection/activation, proactive notification policy, auto-preparation, execution/reminders, follow-up, briefs, backups, health, catch-up, privacy, controls, and honest live-evidence gates; verify documentation paths and examples contain no secrets or private runtime paths.

## 4. Verification and hardening

- [x] 4.1 Add integration/e2e coverage for the V2 acceptance matrix: auto-preparation gates, execution priority, reminders/snooze/stop/caps, briefs, follow-up, propagation, missed-run catch-up, health recovery, automatic backup, migration preservation, and public-repository isolation; verify all new tests pass with temporary private fixtures.
- [x] 4.2 Add adversarial tests for duplicate rediscovery, stale/changed official sources, prompt-injection source text, conflicting profile facts, budget exhaustion, notification spam, quiet hours, large/unsupported attachments, and external-action boundary; verify failures are quiet, safe, and actionable.
- [x] 4.3 Run strict Ruff, strict mypy, full pytest with coverage, build, public-repository audit, and secret scan; verify no existing threshold is lowered and no generated/private runtime data is tracked.
- [x] 4.4 Run read-only codebase-design, Vibe Security, and Code Review Expert gates against the complete product diff and OpenSpec context; adjudicate findings, fix accepted P0/P1 and applicable high security findings, and rerun affected tests.
- [x] 4.5 Inspect Hermes availability and schedules, run the safe local/live checks available without fabricating credentials or external delivery, record exact GATED residuals, run final strict OpenSpec validation, and verify the repository remains synchronized with the V2 change artifacts.
