## Why

OpportunityOS v3 can search adaptively, but its discovery model can become stale between manual profile imports. V3.1 adds a bounded daily personal-intelligence sweep so authorized GitHub, Gmail, and ChatGPT evidence can refresh the existing provenance-backed profile before discovery without creating a second truth model or noisy review inbox.

## What Changes

- Add independently configurable GitHub, Gmail, and ChatGPT personal-source modes, cursors, capability state, authorization state, and health details.
- Add persistent profile-intelligence run state and reconciliation-batch delivery state under the private SQLite database.
- Extend the existing profile observation pipeline with source-record fingerprints, candidate deduplication, subject/assertion classification, temporal metadata, and materiality-aware review behavior.
- Add deterministic orchestration for bounded daily sweeps, partial-source failure isolation, cursor advancement only after safe processing, and honest unsupported-capability handling.
- Reuse the existing profile projection, review resolution, dependency propagation, evaluation invalidation, audit, backup, MCP, CLI, and notification boundaries.
- Add a 05:00 America/Chicago Hermes profile-intelligence schedule before the existing 06:00 global discovery schedule, with reversible activation evidence.
- Extend profile-sync skills, observability, configuration, documentation, migrations, privacy tests, and red-team coverage.

## Capabilities

### New Capabilities

- `profile-intelligence`: bounded daily orchestration, source capability reporting, run state, source health, and discovery handoff.
- `personal-source-sync`: GitHub incremental metadata, Gmail read-only evidence intake, ChatGPT disabled/snapshot-only/continuous capability behavior, cursors, and privacy boundaries.
- `profile-reconciliation`: candidate fingerprints, subject/assertion classification, materiality filtering, temporal preservation, reconciliation batches, and downstream propagation triggers.

### Modified Capabilities

The repository has no durable root `openspec/specs/` tree. Existing V1/V2 profile-ledger, profile-sync, health, automation, and discovery contracts are extended in place; no prior requirement is removed.

## Impact

- Adds typed `profile_intelligence` settings and safe public defaults while preserving existing `profile_sync_github` and snapshot-import callers.
- Adds one forward Alembic migration for personal-intelligence runs, per-source sync state, reconciliation batches, and bounded observation metadata.
- Adds a deep `PersonalIntelligenceService` application seam plus pure classification/materiality/fingerprint policies and injectable read-only adapters for tests and future authorized providers.
- Adds typed MCP/CLI inspection and bounded run controls, a dedicated Hermes orchestration skill, and updates to profile-sync, health, operations, setup, threat-model, and compatibility documentation.
- Does not add Gmail send/write capability, ChatGPT scraping workarounds, a second profile store, a crawler, a web dashboard, a cloud dependency, or any autonomous external action.
