## Purpose

Finds strong category-specific opportunities on schedules without noisy notifications, duplicated work, or unbounded search and model use.

## ADDED Requirements

### Requirement: Hermes-scheduled category scouts
The system MUST support scholarship, fellowship/research, grant/founder, competition/selective technical, and general high-upside scout runs initiated by fresh Hermes cron sessions; an ordinary job scout remains disabled.

#### Scenario: Scholarship run
- **WHEN** a scholarship scout receives mocked official search results
- **THEN** it verifies sponsor evidence, international eligibility and deadline, deduplicates, evaluates, and records the bounded run

### Requirement: Hard run budgets
Every scout MUST enforce configured limits for queries, pages, candidates, deep evaluations, model calls, duration, notifications, and daily aggregates without activating a paid fallback.

#### Scenario: Candidate budget reached
- **WHEN** the maximum candidate count is reached
- **THEN** the scout stops further candidate work, records a budget stop, and preserves completed results

### Requirement: Catch-up window
Each scout MUST record its last successful completion and widen the next search window after a missed-run gap without assuming a sleeping laptop executed jobs.

#### Scenario: Three-day laptop gap
- **WHEN** the previous successful scout ended three days ago
- **THEN** the next query plan records a catch-up window covering the gap within current budgets

### Requirement: Quality gate and quiet digest
Autonomous findings MUST require authoritative current source, open/future status, current deadline, hard eligibility pass, deduplication, value threshold, and confidence threshold before APPLY; runs without material findings MUST emit no digest.

#### Scenario: Quiet run
- **WHEN** a scout finds no new strong opportunity, material change, or urgent review
- **THEN** it records successful completion with a silent delivery result

