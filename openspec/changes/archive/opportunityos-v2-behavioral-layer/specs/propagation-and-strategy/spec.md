## Purpose

Keeps active opportunity decisions aligned with changing profile and official-source truth while making strategy recommendations visible without silently changing policy.

## ADDED Requirements

### Requirement: Material profile changes propagate to dependent opportunities
After a material canonical profile change or reconciliation, the system MUST identify dependent active opportunities, invalidate affected evaluations/actions, reevaluate within budget, rerank current work, and surface only material decision or priority changes.

#### Scenario: Profile change changes a decision
- **WHEN** a changed canonical field affects active opportunity requirements or scoring
- **THEN** the dependent evaluation is made stale, reevaluated safely, and a material resulting decision or priority change may be surfaced

#### Scenario: Unrelated profile change
- **WHEN** a profile update has no dependency on an active opportunity
- **THEN** that opportunity remains current and no notification is generated for it

### Requirement: Material official-source changes invalidate dependent decisions
The system MUST detect changes to deadline, status, eligibility, requirements, application URL, cancellation, or material funding/support during reverification and MUST prevent continued use of stale evaluation state.

#### Scenario: Deadline moves earlier
- **WHEN** official reverification detects a material earlier deadline
- **THEN** the opportunity version changes, dependent evaluation/action state becomes stale, and urgent current-state handling is recalculated

#### Scenario: Cosmetic source change
- **WHEN** only non-material copy or formatting changes
- **THEN** the source version may be recorded without invalidating decisions or notifying the user

### Requirement: Preference learning is advisory and evidence-bounded
The system MAY derive deterministic preference signals only from repeated explicit decision history, MUST expose sample size and evidence, and MUST NOT change scoring weights or notification thresholds without explicit user approval.

#### Scenario: Insufficient history
- **WHEN** a pattern has fewer than the configured evidence threshold
- **THEN** no preference recommendation is generated

#### Scenario: Strategy recommendation
- **WHEN** sufficient repeated decisions support a recommendation
- **THEN** the recommendation is stored for review and core scoring/preference policy remains unchanged until explicit approval
