## Purpose

Maintains a provenance-backed, rebuildable current profile while preserving history and requiring human judgment for genuine conflicts.

## ADDED Requirements

### Requirement: Evidence-first profile ledger
The system MUST store every candidate assertion as a source-linked observation with timestamps, confidence, effective interval, assertion kind, and extraction metadata before it can influence canonical truth.

#### Scenario: Model-proposed fact
- **WHEN** an LLM proposes a profile fact
- **THEN** the system records a pending observation and does not directly mutate a canonical fact

### Requirement: Deterministic reconciliation
The system MUST normalize observations and apply versioned, field-specific authority, recency, interval, duplicate, supersession, conflict, and acceptance rules to build the canonical projection.

#### Scenario: Clear supersession
- **WHEN** the same authoritative source publishes a newer effective GPA value
- **THEN** the newer value becomes canonical, the old observation remains history, and no unnecessary conflict is created

### Requirement: Conflict and downstream blocking
Credible mutually exclusive observations with overlapping validity and no deterministic winner MUST create one deduplicated review item and MUST block decisions that depend on the conflicted hard fact.

#### Scenario: Conflicting graduation dates
- **WHEN** two credible sources provide overlapping May 2027 and May 2028 graduation dates
- **THEN** neither silently wins, one conflict is open, and dependent APPLY decisions are blocked

### Requirement: Human resolution and rebuild
The system MUST record selected or entered values, alternatives, note, effective interval, scope, actor, and time for a resolution; it MUST rebuild the projection deterministically and reevaluate affected active opportunities.

#### Scenario: Resolve a conflict
- **WHEN** the user selects one graduation candidate through CLI or MCP
- **THEN** the resolution and audit event are appended, the projection version changes only if current truth changes, and impacted decisions are reevaluated

### Requirement: Conservative profile adapters
Structured ChatGPT snapshots, local documents, user statements, public web evidence, and GitHub metadata MUST enter as candidate observations; GitHub language or activity MUST NOT establish expertise without independent evidence or approval.

#### Scenario: GitHub language evidence
- **WHEN** GitHub reports that a repository uses Rust
- **THEN** repository and language metadata may be accepted while a proposed "Rust expert" claim remains unverified

