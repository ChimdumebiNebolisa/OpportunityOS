## Purpose

Persist source productivity and machine-readable discovery coverage so fresh Hermes sessions can recover search memory and operators can distinguish healthy deep runs from partial work.

## ADDED Requirements

### Requirement: Source registry records due checks and yield
The system MUST maintain bounded private registry state for repeatedly useful sources, including canonical domain/name, source type and trust class, supported lenses, check cadence, due/last-check state, discovery outcomes, recent/historical yield, change frequency, preferred discovery method, and explicit disable reason.

#### Scenario: A registered source is due
- **WHEN** Hermes reports a safe check outcome for a due source
- **THEN** the system updates the source check timestamps and yield counters and routes novel candidates into the standard opportunity pipeline

#### Scenario: One source fails
- **WHEN** a source check fails or is temporarily unavailable
- **THEN** the failure is stored without disabling unrelated sources or invalidating the whole global run

### Requirement: Coverage reports are complete and machine-readable
Every global run MUST persist run ID, profile projection version, enabled/completed/skipped lenses, skip reasons, baseline counts, adaptive branches, source checks, query/page/model/raw/novel/duplicate/official/deep/decision metrics, saturation stops, budget stops, reallocations, backend failures, material deliveries, and whether the deep-discovery contract was satisfied.

#### Scenario: A full run finishes
- **WHEN** all enabled lens floors, due source checks, required adaptive triggers, deduplication, official verification, and finalist evaluation complete within budget
- **THEN** coverage marks the deep-discovery contract satisfied and exposes the report without raw source bodies or private profile dumps

#### Scenario: A partial run finishes
- **WHEN** required coverage is skipped because of outage, budget exhaustion, authentication failure, or an uncompleted branch
- **THEN** coverage marks the contract incomplete, records the exact safe skip/failure reason, and prevents a normal success claim

### Requirement: Search mechanics remain quiet
Normal delivery MUST surface only material opportunity or execution value. Query counts, branch expansion, source checks, saturation, allocation, and coverage mechanics MUST remain silent unless explicitly requested or an actionable repeated health failure requires notification.

#### Scenario: No material opportunity survives
- **WHEN** a global run produces no new material decision value
- **THEN** the delivery result is `[SILENT]` while coverage remains available through explicit inspection

### Requirement: Search memory is recoverable after downtime
The system MUST use persisted strategy, source, opportunity, rejection, profile-gap, branch, and coverage state when planning a fresh cycle. Missed-run recovery MUST perform one bounded catch-up window rather than replaying every missed cycle.

#### Scenario: The machine was offline
- **WHEN** a new global cycle starts after a configured downtime gap
- **THEN** the system records one bounded catch-up origin, prioritizes freshness and due productive sources, and returns to the normal cadence without replaying each missed occurrence

### Requirement: Private discovery analytics stay outside the public repository
Query strings, yield analytics, source registry state, coverage reports, and live opportunity identifiers MUST remain under the existing private runtime root. Public repository audits MUST not find private discovery state or secrets.

#### Scenario: A public audit runs
- **WHEN** the repository is audited after v3 implementation
- **THEN** search strategy data and private runtime artifacts are absent from tracked files and the audit reports no findings
