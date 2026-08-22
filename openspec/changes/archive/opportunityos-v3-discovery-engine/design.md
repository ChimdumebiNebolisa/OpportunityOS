## Context

OpportunityOS is a production-like V1/V2 brownfield repository with a deterministic Python core, private SQLite, typed MCP/CLI callers, and Hermes-owned scheduling/search/delivery. The v3 PRD explicitly forbids a rewrite, crawler, second scheduler, cloud dependency, or autonomous external action. The existing V2 worktree is intentionally preserved and remains the dependency base.

Planning authorities used for this change:

- OpenSpec owns requirements, artifact dependencies, tasks, and verification context.
- `codebase-design` owns deep-module, interface, seam, locality, and testability pressure-testing.
- `vibe-security` owns the LLM/search-input, private-runtime, ORM/input-validation, budget, and prompt-injection controls.
- `code-review-expert` is reserved for the read-only final diff review.
- `writing-for-agents` remains the authority for agent-facing guidance; no root guidance rewrite is needed unless durable v3 rules require a concise pointer.
- No meaningful UI surface exists in v3; Hermes Desktop and Discord remain external conversational/delivery surfaces, so no frontend specialist is routed.

## Goals and non-goals

Goals:

- Make one global discovery run observable and stateful while reusing V2 `ScoutRun`, opportunity, evaluation, notification, backup, and audit ownership.
- Persist query strategy, branch lineage, source registry, coverage, yield, exploration, saturation, and bounded budget decisions under the private runtime root.
- Provide a small caller-facing discovery interface shared by Hermes, MCP, CLI, and tests.
- Keep adaptive search advisory: LLM/Hermes may propose queries, branches, profile gaps, and similarity seeds; deterministic application code validates and persists only bounded state.
- Replace the five public V2 scout defaults with two configurable global schedules after implementation and local/live-safe inspection.

Non-goals:

- No generic crawler, job-board scraper, search provider, vector database, browser automation, new scheduler, web dashboard, cloud dependency, or outbound action.
- No automatic scoring-weight, eligibility-rule, canonical-profile, or approval-policy mutation.
- No requirement to fake three live cycles, Discord delivery, or external Scheduled Task retirement when the current environment cannot provide evidence.

## Architecture and module interfaces

### Deep discovery module

Add `src/opportunityos/application/discovery.py` as the deep application module and primary seam. It owns deterministic orchestration and persistence for:

- `begin_global(idempotency_key)` -> one run plan with enabled lenses, branch plans, budgets, profile projection version, and bounded catch-up origin;
- `record_query(run_id, branch_id, strategy_id, observation, idempotency_key)` -> updates branch/run/strategy metrics, detects saturation, and returns safe reallocation guidance;
- `expand_branch(run_id, parent_branch_id, proposal, idempotency_key)` -> validates bounded adaptive lineage and creates a child strategy/branch;
- `record_source_check(run_id, source_observation, idempotency_key)` -> upserts a private source registry entry and updates source yield;
- `finish(run_id, completed_lenses, skipped_lenses, errors, idempotency_key)` -> computes honest coverage/deep-contract state and delivery result;
- `coverage(run_id)`, `strategies(filters)`, `sources(filters)`, and `status()` -> bounded inspection without raw source bodies or private profile dumps.

Pure deterministic decisions live in `src/opportunityos/domain/discovery.py`:

- canonical 17-lens list and lens classes;
- safe query normalization/family derivation;
- deterministic yield and recent-yield formulas;
- baseline/exploration/productive allocation;
- saturation thresholds and branch stop decisions;
- adaptive trigger/depth checks;
- deep-contract coverage evaluation;
- safe source-domain canonicalization.

The module calls existing `ScoutService`/`ScoutRunRow` for branch budget/candidate funnel behavior rather than replacing it. Hermes still performs search and interpretation; OpportunityOS receives bounded observations and owns durable state.

### Private persistence

One migration `0003_v3_discovery.py` adds:

- `discovery_runs`: global-cycle state and machine-readable coverage JSON/metrics;
- `query_strategies`: normalized query-family lineage and historical/recent yield;
- `search_branches`: per-run lens branch budgets, recent observations, saturation, and reallocation state;
- `source_registry`: private source cadence, trust, checks, and yield state.

`ScoutRunRow` gains nullable `discovery_run_id` and `branch_id` foreign keys so each global branch remains visible through the existing V2 scout infrastructure. Existing rows remain valid and category scouts continue to work. JSON fields are bounded by application validation and are never used for executable instructions.

### Configuration

Add typed `DiscoverySettings` under `Settings.discovery`, with safe defaults:

- `enabled`, `schedules: ["06:00", "18:00"]`, `lenses`, `max_queries=120`, `max_candidate_pages=250`, `max_deep_evaluations=40`, `max_model_calls=120`, `max_duration_seconds=2700`, `max_notifications=3`, `max_adaptive_depth=3`;
- baseline family floor, productive/strategic/exploratory allocation percentages, exploration floor, source-check budget, daily model/query caps, minimum interval, catch-up days;
- saturation thresholds for zero-novel, zero-qualified/high-duplicate, and recent-yield decisions.

Settings validation MUST require positive floors and allocation percentages totaling 100. V2 `scouts` defaults remain structurally compatible for manual/category callers, while Hermes cron defaults and documentation move to global cycles.

### MCP, CLI, and Hermes

Add least-privilege tools/commands for global begin, query recording, adaptive expansion, source checks, finish, coverage, strategy inspection, source inspection, and discovery status. No new tool can send, submit, upload, purchase, accept terms, withdraw, or mutate remote state.

Update `skills/opportunityos-scout` to:

1. start a fresh session and call `discovery_begin`;
2. follow returned branch plans and call `discovery_record_query` after bounded search batches;
3. call `discovery_expand` only for explicit productive/profile-gap/similarity triggers;
4. call `discovery_record_source_check` for due registry sources;
5. route every candidate through the existing intake/evaluation/scout tools;
6. call `discovery_finish`, returning exactly `[SILENT]` when no material result exists.

Search mechanics, source checks, saturation, and coverage are inspection-only unless an actionable repeated failure is returned.

## Security and privacy controls

- Query templates, source registry, strategy metrics, branch coverage, and opportunity identifiers are private SQLite state; public repository audits must remain clean.
- All MCP proposal inputs use bounded Pydantic models; query text, reasons, domain names, lens names, and IDs have explicit length/allowlist constraints.
- Source pages, raw results, query proposals, and LLM observations are untrusted data. They cannot change settings, budgets, tools, credentials, scoring, eligibility, or external-action permissions.
- No raw source bodies, full profile facts, secrets, or credential values are persisted in discovery metrics or returned by inspection tools.
- SQLAlchemy ORM transactions and idempotency keys protect check-then-write behavior; no raw SQL or arbitrary filesystem paths are introduced.
- Query/page/model/deep-evaluation/source-check/duration/notification caps are enforced from private validated settings and persisted run state, never from source text.
- Adaptive depth is bounded and recursive branch creation is denied beyond policy. Paid fallback is not implemented.
- Discovery candidates reuse existing official-source, current-evaluation, deduplication, delivery, and no-external-action gates.
- Backup-before-migration and supported restore remain the only rollback path.

## Migration and activation plan

1. Preserve the verified pre-v3 private backup and current V2 Hermes schedule evidence.
2. Apply `0003_v3_discovery` through the existing migration path; existing V1/V2 records must remain readable.
3. Run temporary SQLite migration, policy, security, and integration tests.
4. Verify local CLI/MCP/Hermes skill behavior and coverage/status inspection.
5. Pause/remove the five V2 category scout cron jobs only after the two v3 global jobs are prepared; create enabled 06:00/18:00 jobs using `opportunityos-scout` and `--deliver discord`.
6. Run only safe bounded live checks available. Record any incomplete deep run honestly; never fabricate a full-lens or Discord result.
7. Create a post-v3 private backup after activation/evidence collection.

## Verification surfaces

- Pure tests for allocation, floors, yield, normalization, saturation, adaptive depth, source cadence, and deep-contract honesty.
- Integration tests for migration preservation, global plan creation, query metrics, lineage, source updates, reallocation, duplicate/quiet delivery, profile-gap/similarity guards, budget exhaustion, and offline catch-up.
- Contract tests for MCP schemas, CLI commands, Hermes skill references, no external-action names, and private-path isolation.
- Red-team tests for prompt injection, adaptive recursion, noisy/duplicate results, stale/new cycles, broken sources, backend/model failure, exploration starvation, and budget runaway.
- Full Ruff, strict mypy, pytest coverage thresholds, build, public-repository audit, secret scan, strict OpenSpec validation, Hermes schedule inspection, and runtime health.
