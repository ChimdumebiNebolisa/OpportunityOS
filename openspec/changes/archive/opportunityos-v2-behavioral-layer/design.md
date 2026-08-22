## Context

OpportunityOS already has a deterministic domain layer, application services, Alembic-managed SQLite, private-path storage, Hermes-owned scheduling, typed MCP tools, and a CLI. Profile and opportunity versions already make stale evaluations observable, and the existing packet compiler already enforces evidence grounding and a no-external-submission contract. The V2 change therefore adds policy state and orchestration seams around those interfaces instead of introducing a second truth model.

The implementation is non-trivial because it crosses persistence, deterministic policy, private files, Hermes/MCP callers, scheduler state, and operational recovery. The engineering contract at `docs/agents/engineering.md` remains authoritative.

## Goals / Non-Goals

**Goals:**

- Keep canonical truth, eligibility, scoring, packet compilation, and lifecycle transitions owned by existing V1 modules.
- Add deterministic, versioned behavioral policies with observable state for preparation, execution, reminders, briefs, follow-up, propagation, health, and backups.
- Make every policy callable through small application interfaces shared by CLI, MCP, tests, and Hermes skills.
- Preserve private runtime boundaries, idempotency, auditability, migration backups, and failure honesty.
- Enable real Hermes cron configuration when the local Hermes installation is available, while reporting external gating honestly when it is not.

**Non-Goals:**

- No web dashboard, mobile client, parallel Discord client, new scheduler, cloud dependency, new database engine, job scraper, or replacement of V1 scoring/packet/profile architecture.
- No Python code that sends Discord messages, emails, applications, uploads, purchases, accepts terms, withdraws, or mutates remote accounts.
- No automatic mutation of scoring weights or preferences; strategy output remains an approval-gated recommendation.

## Decisions

### 1. Add a policy layer at the application/domain seam

Create pure deterministic functions in `src/opportunityos/domain/behavior.py` for execution priority, reminder severity/materiality, notification ranking, follow-up dates, preparation gates, brief materiality, and preference sample sufficiency. Add cohesive application modules that persist and expose those decisions:

- `application/automation.py` owns scheduler/control state, scout catch-up coordination, automatic-preparation gate/execute, and material delivery selection.
- `application/execution.py` owns completion-leverage queue ranking and reminder state transitions.
- `application/followup.py` owns submission-derived follow-up state and private draft preparation.
- `application/health.py` owns health records, automatic-backup policy/retention, and concise operational status.
- `application/propagation.py` owns bounded dependent reevaluation and advisory strategy snapshots.

These are deep modules with small caller-facing methods. They call existing `DecisionService`, `ApplicationService`, `ScoutService`, and `OperationsService` only where a V1 behavior already owns the invariant; they do not copy those rules. Pure policy functions are tested directly for boundary math, while application behavior is tested through its public methods and temporary SQLite databases.

Alternative rejected: one `V2Service` facade containing all behaviors. It would make unrelated operational, notification, and application changes collide and would be a shallow pass-through interface. Alternative rejected: new repositories or ports for every table; SQLite is the existing local-substitutable adapter and no second production adapter is required.

### 2. Extend configuration with typed, private-safe policy groups

Extend `Settings` with typed groups for `scouts`, `auto_prepare`, `execution`, `notifications`, `briefs`, `followup`, `backup`, and `health`. Public defaults contain only safe thresholds, schedules, and limits. Private configuration may override them through the existing validated merge; secrets and runtime paths remain governed by `load_settings` and `PrivateStorage`.

Scout budget fields remain the only fields passed to a `ScoutRunRow`. Category enablement, schedules, and catch-up days are filtered at the service seam so existing callers that pass `settings.scouts.model_dump()` do not accidentally turn configuration metadata into usage counters.

### 3. Add one forward migration with only behavior state

Add `migrations/versions/0002_v2_behavior.py` for the smallest required state:

- `reminder_states` for one current reminder state per opportunity/action/type;
- `preparation_policy_records` for gate decisions and packet linkage;
- `follow_up_states` for submission timing, prohibition, and draft linkage;
- `health_states` for component status and deduplicated alert state;
- `brief_runs` for silent/delivered digest history;
- `strategy_snapshots` for evidence-bounded weekly recommendations;
- `automation_controls` for persisted local pause/disable controls.

Rows use UUIDs, UTC timestamps, JSON only for bounded structured details, foreign keys where a current V1 record exists, and uniqueness for one current state. The migration creates no replacement V1 table and is reversible for empty/test databases. `Database.migrate` already creates and verifies a pre-migration backup for an existing schema; migration tests will verify that V1 records remain readable after 0002.

### 4. Reuse audit events for notification history and idempotency

Notification delivery is an audit event with a class, fingerprint, and redacted subject identifiers. Daily caps query those events; reminder state stores the last fingerprint for local suppression. This avoids a duplicate notification ledger while keeping delivery evidence in the existing append-only audit history. All mutating policy methods accept idempotency keys where a Hermes retry can repeat work.

### 5. Automatic preparation remains a two-call, approval-safe flow

`auto_prepare_evaluate_gate` is deterministic and side-effect limited to a policy record. `auto_prepare_execute` rechecks the gate in the same call path, accepts only validated grounded claims from Hermes, calls the existing `ApplicationService.prepare`, and records the resulting private packet link. No tool has an external-action capability. A gate failure is a persisted, explainable result rather than a silent success.

### 6. Propagation is explicit, bounded, and called after canonical writes

The existing profile write transaction remains the owner of reconciliation. `profile_revaluate_dependents` is a separate application operation that receives affected field paths, selects active dependent opportunities through requirement field paths, reevaluates only within a configured limit, and returns material decision/priority changes. The same propagation seam is used after official reverification. This avoids nesting a second transaction inside profile reconciliation and gives Hermes scheduled flows a bounded retry point.

### 7. Hermes remains the scheduler and delivery adapter

Python exposes state and rendered, redacted content through typed MCP/CLI operations. Hermes skills own search, model interpretation, session freshness, and actual Discord delivery. Scheduled skills return `[SILENT]` when the application result is silent. Actual cron installation is attempted only through the existing Hermes command adapter and recorded as live evidence; missing Hermes/OAuth/Discord credentials remain `GATED` rather than fabricated as passing.

### 8. Security controls are preventive at every new seam

- Pydantic validates all MCP/CLI inputs; database writes remain ORM/parameterized.
- Imported/source text is evidence only and never becomes tool instructions or scheduler configuration.
- New content fields are bounded; notification fingerprints contain hashes/IDs, not private application text.
- Automatic packet/follow-up files use `PrivateStorage.require_private` and never enter the repository.
- Hermes status probes never inspect credential values; error output is redacted before persistence.
- Daily/model/auto-preparation/weekly-analysis budgets are enforced in application state, not trusted from caller text.
- Existing no-submit/no-send/no-upload invariants remain enforced in service methods and contract tests.

## Risks / Trade-offs

- **[Risk] Existing runtime databases may be from V1 without an Alembic revision.** → Keep `Database.migrate`'s pre-migration backup path, test migration from current V1-shaped databases, and report rollback through the existing restore command.
- **[Risk] Hermes cron syntax or credentials vary by installation.** → Keep schedule definitions in validated private-safe configuration, use the existing read-only command probes, and record `GATED` live evidence instead of claiming activation.
- **[Risk] Repeated scheduled sessions could spam Discord.** → Enforce audit-backed daily caps, quiet hours, fingerprints, escalation, and silent return values before Hermes receives deliverable content.
- **[Risk] A profile/source change could make a packet stale during preparation.** → Recheck evaluation/profile/opportunity versions at gate execution and reuse `ApplicationService` readiness checks before marking READY.
- **[Risk] Strategy metrics could overfit a small history.** → Store evidence counts and only produce recommendations above a configured sample threshold; never apply the recommendation automatically.

## Migration Plan

1. Confirm and record a private pre-V2 backup with integrity and checksum.
2. Run the existing context startup migration to 0002; it creates another verified pre-migration backup before changing an existing schema.
3. Verify V1 tables and audit history remain readable, then exercise new policy tables in a temporary/private test database.
4. If migration fails, stop automation, retain the original database and generated backup, and use the existing empty-target restore path; do not edit SQL manually.

## Open Questions

None. Hermes credentials and live Discord availability affect evidence collection, not the local implementation contract or the selected architecture.
