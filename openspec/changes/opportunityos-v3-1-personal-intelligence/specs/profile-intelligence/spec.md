## Purpose

Provide a bounded, observable daily personal-intelligence loop that refreshes the existing canonical profile before discovery while remaining honest about source capability, failure, and unresolved review work.

## ADDED Requirements

### Requirement: Daily personal-intelligence runs are bounded and observable

The system MUST support one configurable daily personal-intelligence run before the morning discovery cycle. Each run MUST persist its start/end state, profile projection versions, enabled/completed/blocked sources, counters, errors, and status.

#### Scenario: Successful multi-source run
- **WHEN** the scheduled run executes with enabled sources that complete successfully
- **THEN** the run records each completed source, candidate and review counters, the resulting profile projection version, and a successful status

#### Scenario: One source fails
- **WHEN** one enabled source fails authorization or retrieval during a run
- **THEN** the run records that source as blocked or failed, preserves successful evidence from other sources, and finishes with an honest partial status

### Requirement: Source capability and authorization state is inspectable

The system MUST expose configured mode, requested scope, actual capability, authorization state, cursor/high-water mark, last attempt, last success, counters, consecutive failures, status, and a bounded detail code for each personal source.

#### Scenario: Unsupported ChatGPT capability
- **WHEN** ChatGPT is configured for continuous conversation access but the authorized integration cannot expose conversation history
- **THEN** the source is reported as blocked or unavailable with an explicit capability detail and no unsupported read is attempted

#### Scenario: Independent source disablement
- **WHEN** the user disables Gmail while GitHub remains enabled
- **THEN** future runs do not read Gmail, preserve existing Gmail provenance, and continue to inspect GitHub

### Requirement: Cursor advancement requires safe completion

The system MUST advance a source cursor or high-water mark only after that source's records have been safely processed. A failed or interrupted source MUST retain its last successful cursor.

#### Scenario: Successful incremental sync
- **WHEN** a source processes all records through a new high-water mark
- **THEN** the source state persists the new cursor and last-success timestamp

#### Scenario: Processing failure
- **WHEN** candidate extraction or persistence fails before a source batch completes
- **THEN** the source state retains the prior cursor and reports the failure without claiming a successful sync

### Requirement: Morning discovery uses the newest successful profile projection

The system MUST expose the latest successful profile projection version to discovery planning. Discovery MUST continue using the latest available projection without waiting for unresolved human review.

#### Scenario: Profile sweep precedes discovery
- **WHEN** the 05:00 sweep changes the canonical projection before the 06:00 discovery run
- **THEN** the discovery run records and uses the newer projection version

#### Scenario: Review remains unresolved
- **WHEN** a sweep creates an unresolved high-impact review item
- **THEN** discovery proceeds with the current canonical projection and preserves the unresolved review state

### Requirement: Profile review delivery is bounded and deduplicated

The system MUST group material profile review items into a bounded reconciliation batch and MUST suppress duplicate delivery for an unchanged batch fingerprint.

#### Scenario: Material review digest
- **WHEN** a sweep creates multiple material review items
- **THEN** the system creates one bounded batch containing their identifiers and a stable delivery fingerprint

#### Scenario: Duplicate sweep
- **WHEN** a later sweep produces no material change to the same review items
- **THEN** no second equivalent delivery batch is created
