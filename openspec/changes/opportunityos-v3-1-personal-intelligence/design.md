## Context

OpportunityOS already has one append-only `SourceRow`/`ObservationRow` profile ledger, deterministic field reconciliation, human review items, canonical projection versions, bounded dependent reevaluation, private SQLite migration, and V3 discovery state. Existing GitHub metadata sync and ChatGPT snapshot import are public compatibility seams. V3.1 must add orchestration and source state without creating another profile database or bypassing candidate-before-canonical rules.

## Goals / Non-Goals

**Goals:**

- Add a single `PersonalIntelligenceService` seam shared by Hermes, MCP, CLI, and tests.
- Persist source capability/configuration state, cursors, high-water marks, run counters, and reconciliation batch state privately.
- Make source adapters injectable and honest: real GitHub metadata can reuse the current client; Gmail and continuous ChatGPT access remain capability-gated until an authorized provider is supplied.
- Feed every accepted record through existing source and profile services, preserve historical observations, and expose changed fields for bounded propagation.
- Provide a small record-ingestion interface so Hermes can read authorized Gmail/ChatGPT data and submit bounded candidate proposals without OpportunityOS storing a corpus dump.

**Non-Goals:**

- No Gmail OAuth client, ChatGPT scraping workaround, or new cloud/provider dependency is introduced in this change.
- No direct canonical writes, external writes, outbound email, GitHub mutations, or ChatGPT conversation mutations.
- No replacement of the existing profile service, review resolution, discovery service, or propagation service.

## Decisions

### 1. One orchestration module, existing profile ledger

Add `application/personal_intelligence.py` as a deep module. It owns run lifecycle, source-state transitions, bounded record ingestion, cursor advancement, material review batching, and status. It delegates source creation and candidate projection to `ProfileService`, and delegates changed-field reevaluation to `PropagationService`.

Alternative rejected: a second personal-profile repository. That would violate the V1/V2 canonical-truth invariant and make projection versions ambiguous.

### 2. Adapter protocol with capability-gated defaults

Add a small persistence-neutral adapter protocol returning capability state and bounded `PersonalSourceRecord` values. The default GitHub adapter wraps the existing `GitHubClient`; the default Gmail adapter reports unavailable until an authorized read-only provider is injected; the default ChatGPT adapter supports explicit snapshot ingestion and reports continuous capability honestly. Tests use deterministic fake adapters.

Alternative rejected: adding provider SDKs or browser automation now. The PRD requires actual capability reporting and forbids unsupported scraping workarounds.

### 3. Minimal private schema extension

Migration `0004_v3_1_personal_intelligence.py` adds:

- `profile_intelligence_runs` for bounded daily run state and counters;
- `personal_source_sync_states` keyed by source type for modes, requested/actual capabilities, cursor, high-water mark, timestamps, failures, and detail codes;
- `reconciliation_batches` for bounded material review delivery fingerprints;
- `ObservationRow` columns for normalized content fingerprint, subject identity, and source event timestamp.

Existing `SourceRow`, `ObservationRow`, `ReviewItemRow`, `CanonicalFactRow`, and `AuditEventRow` remain authoritative. The migration uses the existing Alembic path, checks existing columns, and preserves V1/V2/V3 rows on upgrade and downgrade.

### 4. Deterministic classification and fingerprinting

Add pure functions in `domain/personal_intelligence.py` for source-mode validation, assertion/subject classification, normalized content fingerprints, candidate fingerprints, and materiality decisions. Source text is data only; classifications are bounded inputs and never control tools, settings, budgets, or credentials.

The observation schema is widened from the original three assertion labels to bounded strings so source-specific classes such as `correction`, `hypothetical`, `quoted`, `third_party`, and `assistant_summary` can be preserved. The profile authority policy remains the final deterministic selector.

### 5. Cursor and partial-failure semantics

`begin()` snapshots the current profile projection. `record_source()` validates the source mode, deduplicates records and observations, submits candidates through `ProfileService`, and advances that source cursor only after the record batch commits. Source failures update only that source state and the run's blocked-source list. `finish()` creates one reconciliation batch from newly created material reviews and records the resulting profile projection.

Alternative rejected: advancing cursors before extraction. That would lose evidence on model/provider failure and violate recovery requirements.

### 6. Least-privilege interfaces

Expose only status, capability, sync-state, begin, record, finish, and bounded review-batch operations through MCP/CLI. No new interface can send, post, upload, purchase, accept terms, or mutate an external system. All text, locators, IDs, counts, and JSON payloads are bounded by Pydantic validation.

### 7. Schedule activation remains reversible

Add the 05:00 default to Hermes documentation and a dedicated `opportunityos-profile-intelligence` skill. Actual schedule creation is performed only after local checks and private backup evidence; unsupported Gmail/ChatGPT capabilities remain visible as blocked rather than being represented as successful live sync.

## Risks / Trade-offs

- [Provider capability unavailable] → Persist blocked state and continue other sources; do not fake continuous Gmail or ChatGPT access.
- [Existing profile reconciliation is field-level] → Keep source-record and observation fingerprints at the adapter/orchestration boundary, while reusing existing field reconciliation for canonical projection.
- [A source record may contain sensitive text] → Store only bounded evidence excerpts/metadata and hashes; never persist full message or conversation corpora in public files or discovery metrics.
- [Automatic propagation could be expensive] → Expose changed fields and call existing bounded propagation limits; unresolved reviews never trigger propagation.
- [Migration failure] → Create a verified private backup before upgrade and rely on the existing supported restore path; never hand-edit production SQLite.
- [Real Gmail/ChatGPT credentials are external] → Keep those adapters capability-gated and test with fakes; record live evidence as gated until authorized integrations are actually available.

## Migration Plan

1. Create and integrity-check a private pre-v3.1 backup.
2. Apply `0004_v3_1_personal_intelligence` through `ApplicationContext` migration.
3. Run migration-preservation and focused privacy/failure tests.
4. Inspect and update private profile-source settings without committing them.
5. Install/refresh the local profile-intelligence skill and add the 05:00 Hermes schedule only after local probes pass.
6. Run safe synthetic/fake-adapter sweeps and inspect status, cursors, reviews, and coverage.
7. Create a verified post-v3.1 private backup.

Rollback uses the existing supported private backup restore path and schedule pause; no manual SQLite edits are permitted.

## Open Questions

- The current Hermes installation exposes MCP and Discord, but the live Gmail and ChatGPT provider surfaces must be verified at activation time. The adapter contract intentionally leaves those provider implementations outside this repository change until capability is confirmed.
