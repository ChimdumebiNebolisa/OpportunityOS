## Why

OpportunityOS v1 already protects canonical profile and opportunity truth, but it still depends on the user to run scouts, notice unfinished high-value work, request preparation, and remember follow-up or operational maintenance. V2 adds the smallest durable behavioral layer needed to make safe, reversible work proactive while preserving the deterministic core, local SQLite state, Hermes scheduling, and explicit approval gates for every external action.

## What Changes

- Add deterministic policy modules for automatic preparation gates, execution priority, reminder escalation/snooze/stop, material notification selection, daily/evening/weekly briefs, follow-up eligibility, profile/opportunity change propagation, preference signals, and bounded missed-run catch-up.
- Extend private SQLite state through an Alembic migration for reminder, preparation-policy, follow-up, health, brief-run, and strategy-snapshot records only where existing v1 tables cannot represent the behavior.
- Add configurable private/public-safe settings for automation schedules, budgets, notifications, auto-preparation, follow-up, backups, health, and quiet hours; keep secrets and runtime data outside the repository.
- Extend the existing application services, CLI, typed MCP server, and Hermes skills with least-privilege v2 operations for execution, reminders, preparation gates, follow-up drafts, briefs, health, automatic backups, and dependent profile reevaluation.
- Preserve the v1 ingestion, reconciliation, eligibility, scoring, application-packet, lifecycle, scout, storage, and external-action safety mechanisms; only add integration seams where current behavior varies or a v2 policy requires an observable interface.
- Document scheduler configuration and inspection, proactive notification policy, automation controls, operational recovery, privacy limits, and live-evidence boundaries.
- Add focused migration, policy, integration, contract, and adversarial tests without lowering existing lint, type, coverage, build, or security thresholds.

## Capabilities

### New Capabilities

- `proactive-automation`: bounded scheduled work, delivery gating, cost budgets, quiet runs, and missed-run catch-up.
- `auto-preparation`: deterministic high-confidence gates and private packet preparation with no external submission.
- `execution-and-reminders`: completion-leverage priority, one-primary-action selection, reminder escalation, daily caps, quiet hours, snooze, stop, and duplicate suppression.
- `briefs-and-follow-up`: material daily/evening/weekly briefs and grounded private follow-up drafts for explicitly submitted opportunities.
- `propagation-and-strategy`: profile/opportunity change propagation, deterministic preference signals, and approval-gated strategy recommendations.
- `health-and-operations`: health watchdog state, automatic backup scheduling/retention, operational controls, and concise status reporting.

The new capabilities explicitly extend the corresponding V1 contracts in
`openspec/changes/build-opportunityos-v1/specs/`; no V1 requirement is
replaced or deleted.

## Impact

- Existing Python modules under `src/opportunityos/application`, `domain`, `config`, `infrastructure`, `mcp`, and `cli` will gain cohesive policy/application interfaces; v1 callers remain compatible.
- `migrations/versions` will receive one forward migration that preserves all existing private data and is tested from an empty database and a v1-shaped database.
- Existing Hermes skills will be extended where possible; new behavioral skills will be added only when a current skill cannot keep a small, clear interface.
- Public documentation, examples, and configuration guidance will be updated; no custom dashboard, second scheduler, cloud dependency, external submission path, or new database engine is introduced.
- Live acceptance evidence requiring real Hermes, Discord, OAuth, or network services will be recorded separately and never fabricated; local deterministic boundaries remain fully testable without credentials.
