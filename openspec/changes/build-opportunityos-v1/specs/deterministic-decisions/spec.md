## Purpose

Produces replayable eligibility, value, queue, action, and lifecycle outcomes from validated evidence and versioned rules.

## ADDED Requirements

### Requirement: Versioned requirement predicates
The system MUST validate extracted requirements into a versioned deterministic predicate language, retain official text and evidence, and route unrepresentable or ambiguous hard requirements to review rather than pass.

#### Scenario: Unknown citizenship rule
- **WHEN** an unofficial source claims international eligibility but official wording is ambiguous
- **THEN** the hard requirement is unknown or ambiguous and the overall decision is REVIEW REQUIRED

### Requirement: Deterministic eligibility
Every hard requirement MUST evaluate to pass, fail, unknown, conflicted, or not applicable from canonical facts; any hard fail MUST produce INELIGIBLE/PASS and any hard unknown or conflict MUST prevent APPLY.

#### Scenario: Citizenship failure overrides score
- **WHEN** official requirements demand citizenship incompatible with the canonical profile
- **THEN** the opportunity is INELIGIBLE and PASS regardless of subjective component values

### Requirement: Reproducible scoring and confidence
The system MUST validate evidence-linked 0-10 subjective assessments, calculate the configured weighted 0-100 raw score, deterministic effort penalty, net score, confidence, and decision while recording all input and ruleset versions.

#### Scenario: Score replay
- **WHEN** identical profile, opportunity, requirements, assessments, and ruleset versions are evaluated twice
- **THEN** numeric scores, confidence, eligibility, and decision are identical while evaluations remain append-only

### Requirement: Global time-aware action queue
The system MUST rank ready actions across opportunity types from value, urgency, readiness, and available-time fit, exclude blocked/expired actions, and return one defensible primary action plus at most one necessary fallback.

#### Scenario: Thirty-minute request
- **WHEN** the user requests one action with 30 minutes available
- **THEN** the system returns a ready action fitting the time or the highest-value completable sub-action with reason, deadline, prepared assets, and exact human step

### Requirement: Enforced lifecycle
The system MUST validate all opportunity and application state transitions atomically and MUST require evidence for READY, user confirmation for SUBMITTED, and authoritative input for ACCEPTED or REJECTED.

#### Scenario: Invalid submitted jump
- **WHEN** a caller attempts to mark an unprepared application SUBMITTED without confirmation and timestamp
- **THEN** the transition fails clearly and no partial state or decision event is written

