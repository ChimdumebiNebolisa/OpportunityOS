## Purpose

Prepares private, opportunity-specific application material while making every professional claim traceable to accepted evidence.

## ADDED Requirements

### Requirement: Private application packet
On user request, the system MUST create a private packet containing a decision brief, current official link/deadline, eligibility and requirements checklists, evidence map, drafts, recommendations, missing questions, submission checklist, and state.

#### Scenario: Prepare an eligible opportunity
- **WHEN** the user requests preparation for a verified eligible opportunity
- **THEN** packet artifacts are stored outside the repository and identify the profile and opportunity versions used

### Requirement: Claim grounding
Every professional claim MUST reference verified canonical facts or explicitly application-approved contextual evidence; unsupported claims MUST be rejected or visibly marked missing.

#### Scenario: Unsupported draft claim
- **WHEN** a draft asks to include an accomplishment absent from accepted evidence
- **THEN** the compiler omits or marks the claim missing and cannot mark the packet READY

### Requirement: Readiness reverification
Before READY, the system MUST verify the official application is open, deadline current, requirements unchanged, eligibility valid, and all required claims grounded.

#### Scenario: Deadline passed during preparation
- **WHEN** reverification finds that the official deadline has passed
- **THEN** READY is refused and the opportunity transitions to EXPIRED when appropriate

### Requirement: Human-only external action
The system MUST NOT expose a capability that submits forms, uploads to external sites, sends messages, purchases, accepts terms, or otherwise completes an external action.

#### Scenario: Packet completion
- **WHEN** every private artifact is complete
- **THEN** the system returns the official link and exact manual checklist without performing the submission

