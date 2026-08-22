## 1. Planning, configuration, and persistence

- [x] 1.1 Add typed `DiscoverySettings` and safe public defaults for the 17 lenses, 06:00/18:00 schedules, global budgets, allocation percentages, exploration floor, adaptive depth, source checks, saturation, daily caps, and catch-up; verify validation rejects invalid allocation totals and unsafe limits.
- [x] 1.2 Add `discovery_runs`, `query_strategies`, `search_branches`, and `source_registry` SQLAlchemy rows with bounded JSON fields, foreign keys, indexes, uniqueness constraints, and UTC timestamps; extend `ScoutRunRow` with nullable global/branch links.
- [x] 1.3 Add `0003_v3_discovery.py` with upgrade/downgrade support and V2 preservation; verify empty migration, V2-shaped migration, private pre-v3 backup, and rollback safety.
- [x] 1.4 Add pure `domain/discovery.py` policies for lens classes, query normalization/families, yield/recent-yield, allocation/floors, saturation, adaptive depth, source cadence, and deep-contract coverage; verify boundaries with focused tests.

## 2. Stateful discovery behavior

- [x] 2.1 Implement global run planning with all enabled lenses, two baseline strategy families per primary lens, profile projection version, current budget, and one bounded missed-run catch-up origin.
- [x] 2.2 Implement query observation recording with deterministic counters, strategy metrics, recent observations, global/per-branch/model/page/time caps, and idempotent updates.
- [x] 2.3 Implement adaptive branch expansion with parent/seed lineage, bounded reason/query fields, depth limits, productive/profile-gap/similarity trigger metadata, and safe rejection of recursive or malformed proposals.
- [x] 2.4 Implement exploration/productive/strategic allocation, per-lens baseline floors, deterministic branch priority, and unused-budget reallocation after saturation or early stop.
- [x] 2.5 Implement deterministic saturation for no-novel, high-duplicate/no-qualified, depth, and due-source completion signals without stopping baseline coverage prematurely.
- [x] 2.6 Implement private source-registry upsert/check/yield behavior, due-source selection, source failure isolation, recent/historical yield, and explicit disable state.
- [x] 2.7 Implement honest global finish/coverage state including completed/skipped lenses, skip reasons, adaptive/source/saturation/reallocation metrics, deep-contract satisfaction, and `[SILENT]` delivery semantics.
- [x] 2.8 Reuse existing opportunity normalization, duplicate/cycle identity, official-source, eligibility, evaluation, portfolio, auto-preparation, notification, and audit interfaces; verify similarity never changes final scoring and profile-gap never mutates canonical facts.

## 3. Existing interface and activation integration

- [x] 3.1 Extend ScoutService/ScoutRun persistence so global branches remain bounded, auditable, compatible with V2 category calls, and recoverable through existing status/abort behavior.
- [x] 3.2 Add typed MCP tools for discovery begin, query observation, adaptive expansion, source checks, finish, coverage, strategies, sources, and status; verify schemas, idempotency, redaction, and no external-action capability.
- [x] 3.3 Add matching CLI commands and help output for global discovery planning, progress, expansion, source registry, coverage, strategy state, and status.
- [x] 3.4 Update the Hermes scout skill for fresh-session state loading, branch budgets, lens coverage, adaptive/source/saturation calls, candidate funnel reuse, `[SILENT]`, prompt-injection resistance, and honest incomplete runs.
- [x] 3.5 Replace public V2 staggered scout defaults/documentation with configurable 06:00/18:00 global cycles; inspect/activate two Hermes jobs only after local checks and preserve a reversible schedule record.
- [x] 3.6 Update README, operations, data model, threat model, Hermes setup, cron examples, and compatibility/acceptance documentation with v3 state, controls, coverage inspection, and live-evidence boundaries.

## 4. Verification, hardening, and evidence

- [x] 4.1 Add integration coverage for global planning, all lens floors, query/source metrics, adaptive lineage, profile-gap/similarity branches, saturation, reallocation, budget stops, duplicate/new-cycle identity, silent runs, and catch-up.
- [x] 4.2 Add adversarial/red-team coverage for 500 noisy results, duplicate floods, stale/dead/renamed/new-cycle sources, prompt injection, broken sources, search/model outages, recursion, exploration starvation, overlapping runs, and notification caps.
- [ ] 4.3 Run full Ruff, strict mypy, pytest with overall/domain coverage gates, build, migration tests, public-repository audit, pip-audit/secret scan, and git diff hygiene; verify no V1/V2 threshold is lowered.
- [x] 4.4 Run read-only codebase-design, Vibe Security, and Code Review Expert checks against the product diff and OpenSpec context; adjudicate findings, fix accepted P0/P1 and applicable security findings, and rerun affected gates.
- [ ] 4.5 Inspect Hermes MCP/skills/schedules and local health, run safe bounded global/partial/silent checks without fabricating credentials or full-lens completion, record exact GATED residuals, and create a verified post-v3 private backup.
- [x] 4.6 Run final strict OpenSpec validation, confirm all tasks/spec scenarios are synchronized, and leave the v3 change active rather than archiving it unless explicitly requested.
