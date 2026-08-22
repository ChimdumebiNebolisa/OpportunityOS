## Why

OpportunityOS v1/v2 preserve canonical opportunity truth and execute safe proactive workflows, but their staggered category scouts do not remember search performance or provide full twice-daily coverage. V3 adds a durable discovery strategy layer so Hermes can search broadly, adapt from productive results, preserve exploration, and remain honest about incomplete coverage without replacing the existing scout, ledger, evaluation, or delivery architecture.

## What Changes

- Replace the public default scout cadence with configurable global discovery cycles at 06:00 and 18:00 America/Chicago while preserving Hermes as the scheduler and V2 category compatibility.
- Add persistent query strategies, query-family metrics, adaptive branch lineage, source-registry yield state, and machine-readable global-run coverage.
- Add deterministic allocation, exploration floors, saturation stops, bounded adaptive depth, productive-budget reallocation, source-check budgets, and daily/global cost controls.
- Add profile-gap and similar-to-valued-opportunity discovery signals that influence search allocation only and never mutate canonical profile facts or scoring weights.
- Extend the existing ScoutRun infrastructure so global branches retain V2 budgets, candidate funnel, duplicate suppression, official-source gates, evaluation, auto-preparation, delivery caps, and audit history.
- Add typed MCP/CLI interfaces and Hermes scout guidance for global planning, query progress, adaptive expansion, source checks, coverage inspection, and honest completion.
- Add one forward migration from the V2 schema, private runtime backup/rollback evidence, focused policy/integration/adversarial tests, and synchronized operational documentation.

## Capabilities

### New Capabilities

- `discovery-strategy`: global discovery cycles, required lenses, strategy registry, query families, adaptive lineage, profile-gap and similarity branches, exploration, saturation, and budget allocation.
- `discovery-coverage`: durable source registry, source checks, run coverage reports, deep-discovery honesty, metrics, and status inspection.

### Modified Capabilities

The repository has no durable root `openspec/specs/` tree; this change extends the completed V1/V2 contracts under `openspec/changes/` for scouts, proactive automation, execution, health, and the canonical opportunity pipeline. No V1/V2 requirement is removed; V3 supersedes only the V2 default scout cadence and discovery depth.

## Impact

- Adds typed `discovery` settings and safe defaults while retaining V2 `scouts` settings for compatibility.
- Adds private SQLite tables for global discovery runs, query strategies, search branches, and source registry entries through one Alembic migration.
- Extends application, domain, MCP, CLI, Hermes skill, documentation, and test surfaces without adding a web dashboard, crawler, job scraper, cloud dependency, vector database, or external-action capability.
- Requires private Hermes schedule replacement from the five staggered V2 scout jobs to two global jobs after local and live-safe verification; external Discord delivery remains evidence-gated.
