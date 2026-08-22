## Purpose

Runs bounded, profile-aware OpportunityOS work on a schedule and delivers only material results while recovering safely from local downtime.

## ADDED Requirements

### Requirement: Scheduled scouts use the existing deterministic intake pipeline
The system MUST support configurable recurring scout categories for scholarships, fellowships/research, grants/founder programs, competitions/selective technical programs, and general high-upside opportunities. Each run MUST use the existing ingestion, official-source verification, eligibility, deduplication, evaluation, and delivery gates.

#### Scenario: Supported category run
- **WHEN** a configured category scout starts
- **THEN** it loads current canonical profile state, applies bounded discovery and deterministic prefiltering, and sends finalists through the same opportunity pipeline as manual intake

#### Scenario: Unsupported category
- **WHEN** a caller requests a category outside the configured supported set
- **THEN** the run is rejected with a safe validation error and no candidate or notification state is written

### Requirement: Scout work is progressively bounded
Each scheduled run MUST enforce query, page, model-call, deep-evaluation, duration, notification, and daily model budgets. Budget exhaustion MUST persist a stopped run without retry loops.

#### Scenario: Budget exhaustion
- **WHEN** a run reaches any configured budget
- **THEN** it records the stopped reason and counters, prevents further work for that run, and remains silent unless repeated failures make health materially worse

### Requirement: Quiet and duplicate delivery is the default
The system MUST produce a silent result when no candidate clears the material delivery gate. An unchanged previously delivered opportunity MUST remain silent unless a material deadline, status, eligibility, decision, packet-readiness, execution-risk, or cycle change occurs.

#### Scenario: Quiet scout
- **WHEN** a bounded run has no new or materially changed candidate above the delivery gate
- **THEN** the run completes successfully with a silent delivery result and no empty notification

### Requirement: Missed scheduled work has bounded catch-up
On the next eligible run after local downtime, the system MUST inspect the last successful run for the category, search only within the configured catch-up window, deduplicate results, and avoid replaying each missed schedule occurrence.

#### Scenario: Restart after missed intervals
- **WHEN** the last successful category run is older than the catch-up threshold
- **THEN** the next run records a bounded catch-up window, performs at most one catch-up pass, and notifies only for material results or actionable failures
