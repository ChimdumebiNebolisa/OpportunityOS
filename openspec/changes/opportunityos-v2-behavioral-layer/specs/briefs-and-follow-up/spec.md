## Purpose

Creates concise material-only briefs and private follow-up drafts so the user sees the most valuable current work without automatic outbound communication.

## ADDED Requirements

### Requirement: Briefs contain only material current information
Daily, evening-rescue, and weekly-strategy runs MUST select at most the configured item count, prioritize new/changed/high-value unfinished/follow-up/review content, and return a silent result when no section is material.

#### Scenario: Material daily brief
- **WHEN** at least one new, changed, unfinished, follow-up, or blocking-review item clears its materiality rule
- **THEN** the system persists a brief run and returns a concise prioritized brief

#### Scenario: Quiet day
- **WHEN** no brief section contains material information
- **THEN** the brief run is recorded as silent and no notification is delivered

### Requirement: Follow-up eligibility is explicit and bounded
The system MUST calculate follow-up eligibility only for explicitly SUBMITTED opportunities with no outcome, a reached earliest follow-up date, and no prohibition or completed follow-up. Official response windows and explicit no-contact instructions MUST change the result.

#### Scenario: Follow-up becomes due
- **WHEN** an explicitly submitted opportunity reaches its earliest allowed follow-up date without an outcome
- **THEN** the opportunity becomes FOLLOW_UP_DUE and the system may prepare a private draft

#### Scenario: Follow-up prohibited
- **WHEN** the official source prohibits contact or provides a later response boundary
- **THEN** the system suppresses or defers follow-up and records the reason

### Requirement: Follow-up drafts remain private
Follow-up preparation MUST ground the draft in accepted opportunity/application evidence and MUST NOT send, post, or otherwise deliver the draft externally.

#### Scenario: Draft prepared
- **WHEN** follow-up is due and local preparation is enabled
- **THEN** a private evidence-linked draft is stored and the user is told that nothing was sent
