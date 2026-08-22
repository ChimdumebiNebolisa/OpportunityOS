## 1. Contracts and deterministic policy

- [x] 1.1 Add typed `ProfileIntelligenceSettings`, safe public defaults, independent source modes/scopes, 05:00 schedule, bounded lookback/record/model/duration/review limits, and validation tests for invalid modes and unsafe limits.
- [x] 1.2 Add bounded Pydantic inputs for personal-intelligence begin, source record, candidate observation, capability, sync state, finish, and reconciliation-batch inspection; verify invalid locators, text, cursors, counts, and assertion classes are rejected.
- [x] 1.3 Add pure personal-intelligence policies for source-mode/capability state, subject/assertion classification, content/candidate fingerprints, exact-agreement silence, and materiality decisions; verify hypothetical, quoted, assistant-authored, third-party, duplicate, and material-change cases.

## 2. Private persistence and migration

- [x] 2.1 Add `ProfileIntelligenceRunRow`, `PersonalSourceSyncStateRow`, and `ReconciliationBatchRow` with bounded JSON, indexes, private timestamps, and safe status fields; verify metadata creation and serialization.
- [x] 2.2 Extend `ObservationRow` with content fingerprint, subject identity, and source event timestamp while preserving existing rows and profile reconciliation behavior.
- [x] 2.3 Add `0004_v3_1_personal_intelligence.py` with upgrade/downgrade support, existing-column guards, V2/V3 preservation, and rollback tests.

## 3. Source adapters

- [x] 3.1 Add the injectable personal-source adapter protocol and capability/result records; verify source failures are isolated and no adapter exposes external write operations.
- [x] 3.2 Extend GitHub personal metadata handling with cursor/high-water filtering and objective evidence boundaries while preserving the existing `profile_sync_github` compatibility path.
- [x] 3.3 Add a bounded read-only Gmail adapter seam with disabled/continuous modes, relevant-record filtering, attachment/body limits, and honest unavailable/auth failure behavior.
- [x] 3.4 Add ChatGPT adapter behavior for disabled, snapshot-only, and capability-gated continuous modes with explicit user-vs-assistant/assertion classification and no corpus dump.

## 4. Personal-intelligence orchestration

- [x] 4.1 Implement `PersonalIntelligenceService.begin` with automation control checks, source-state initialization, projection snapshot, overlap protection, and idempotency.
- [x] 4.2 Implement source record ingestion through `ProfileService`, source/observation deduplication, bounded counters, cursor advancement only after success, and per-source failure isolation.
- [x] 4.3 Implement material review batching, exact-agreement suppression, profile projection tracking, bounded propagation requests, and honest `finish`/status responses.
- [x] 4.4 Extend health and operations status with personal-intelligence runs, source capabilities, cursors, failures, pending review counts, and next/last sweep information.

## 5. MCP, CLI, Hermes, and documentation

- [x] 5.1 Add least-privilege MCP tools for personal-intelligence begin, source record, finish, status, capabilities, sync state, review batch, and source controls; verify the catalog contains no external write capability.
- [x] 5.2 Add matching CLI commands for intelligence status/run/finish, source inspection and controls, and bounded review inspection; verify concise help and JSON output.
- [x] 5.3 Extend `opportunityos-profile-sync` and add `opportunityos-profile-intelligence` guidance for fresh-session state loading, source modes, cursor safety, candidate-before-canonical behavior, and quiet delivery.
- [x] 5.4 Update README, operations, data model, threat model, Hermes setup, cron examples, compatibility, and privacy documentation for the 05:00 sweep and capability-gated personal sources.
- [x] 5.5 Inspect and activate the reversible 05:00 Hermes schedule only after local probes and a private pre-activation backup; record exact job state and unsupported external capabilities.

## 6. Verification and completion

- [x] 6.1 Add focused unit/integration tests for settings, fingerprints, assertion classification, migration preservation, cursor non-advancement, duplicate silence, material review, temporal history, partial failure, and propagation.
- [x] 6.2 Add red-team tests for phishing/newsletters, forwarded/quoted/third-party content, assistant hallucinations, stale bootstrap records, auth failure, unsupported ChatGPT capability, source isolation, prompt injection, and corpus/privacy leakage.
- [x] 6.3 Run focused tests, full quality gates, build, public-repository audit, dependency/secret scanning, and strict OpenSpec validation without lowering existing thresholds.
- [x] 6.4 Create and integrity-check a post-v3.1 private backup, inspect runtime health and schedules, record live evidence/gated capabilities honestly, and leave the OpenSpec change active until external acceptance is complete.
