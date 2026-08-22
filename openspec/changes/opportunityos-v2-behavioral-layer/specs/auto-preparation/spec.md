## Purpose

Prepares private, grounded application materials automatically for exceptionally strong current opportunities while preserving all V1 readiness and external-action safeguards.

## ADDED Requirements

### Requirement: Automatic preparation requires every configured quality gate
Automatic preparation MUST require a current APPLY decision, deterministic eligibility, a verified official source within the freshness window, a future confirmed deadline, sufficiently complete requirements, a current profile evaluation, configured score and confidence thresholds, no blocking review, no PASS or WITHDRAW decision, a preparation-permitted lifecycle, and available preparation budget.

#### Scenario: Strong opportunity passes the gate
- **WHEN** every automatic-preparation gate is true
- **THEN** the system re-verifies the official source, records a passing policy decision, and permits private packet preparation

#### Scenario: One required gate fails
- **WHEN** any gate is false or required state is stale
- **THEN** the system records a failed policy decision with a reason and does not create or refresh an automatic packet

### Requirement: Automatic preparation is private and grounded
Automatic preparation MUST use only accepted or verified evidence, preserve evidence links and generation metadata, and write artifacts only under the private runtime root. It MUST reuse the existing packet readiness rules.

#### Scenario: Packet is prepared
- **WHEN** a passing gate is executed within budget
- **THEN** the resulting packet and policy record are private, evidence-linked, auditable, and READY only if all existing readiness checks pass

### Requirement: Automatic preparation never performs external action
Automatic preparation MUST NOT submit, upload, send, purchase, accept terms, withdraw, or otherwise mutate an external system.

#### Scenario: External action would be required
- **WHEN** preparation would require interacting with an external application form
- **THEN** the system stops at local draft artifacts and reports that explicit human action remains required
