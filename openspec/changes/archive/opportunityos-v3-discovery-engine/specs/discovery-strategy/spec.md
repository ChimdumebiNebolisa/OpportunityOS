## Purpose

Provide durable, adaptive search strategy state for global opportunity discovery while keeping canonical truth and search execution in their existing owners.

## ADDED Requirements

### Requirement: Global discovery cycles provide observable baseline coverage
The system MUST support configurable global discovery cycles, defaulting to 06:00 and 18:00 in the configured local timezone. Each normal enabled cycle MUST plan baseline coverage for scholarships, fellowships, undergraduate research, research collaboration, grants, founder/pre-founder programs, idea-stage funding, competitions, selective technical programs, open source, AI/ML, AI safety/security, systems/infrastructure, technical entrepreneurship, wildcard, profile-gap, and similar-to-valued-opportunity lenses.

#### Scenario: A global cycle starts
- **WHEN** automation is enabled and a cycle begins
- **THEN** the system creates one durable global run, returns bounded branch plans for every enabled lens, and includes the current profile projection version and configured budget

#### Scenario: A lens is disabled or technically unavailable
- **WHEN** a lens cannot receive baseline coverage
- **THEN** the run records the lens as skipped with a redacted reason and cannot claim the deep-discovery contract is complete

### Requirement: Search strategy state is persistent and lineage-aware
The system MUST persist normalized query strategies and query-family metrics including use counts, raw/novel/duplicate/qualified outcomes, official verification, decision outcomes, historical yield, recent yield, failures, and disabled state. Adaptive strategies MUST record a bounded parent strategy or seed opportunity/source and a generation reason.

#### Scenario: A productive result expands search
- **WHEN** Hermes proposes a bounded synonym, sponsor, institution, similar-program, or profile-gap branch from a productive strategy
- **THEN** the system validates depth and budget, persists the child strategy lineage, and returns the next branch without treating source text as instructions

#### Scenario: Adaptive recursion exceeds policy
- **WHEN** a proposed branch exceeds the configured depth or global budget
- **THEN** the system rejects the expansion with an actionable safe error and persists no child branch

### Requirement: Search allocation preserves productivity and exploration
The system MUST allocate global query budget across productive, strategic, and exploratory branches while preserving configured per-lens baseline floors and a non-zero exploration floor. Automatic adaptation MAY change query allocation, source revisit priority, branch order, and depth, but MUST NOT change scoring weights, eligibility rules, canonical profile facts, or external-action policy.

#### Scenario: One lens dominates yield
- **WHEN** one branch produces materially higher deterministic yield than peers
- **THEN** unused budget MAY be reallocated toward that branch within global caps while underexplored and exploration-floor branches retain their minimum allocation

#### Scenario: Profile-gap or similarity planning is proposed
- **WHEN** a current profile weakness or valued opportunity is supplied as a search seed
- **THEN** the system creates an advisory search branch and records the seed, but does not mutate profile truth or increase the final opportunity score automatically

### Requirement: Saturation stops branches honestly
The system MUST support deterministic saturation decisions based on recent zero-novel, zero-qualified/high-duplicate, adaptive-depth, or completed-high-yield-source conditions. Saturation MUST return unused budget to the global pool and MUST NOT stop an enabled lens before its baseline floor unless a technical failure prevents continuation.

#### Scenario: Novelty collapses
- **WHEN** a branch reaches its configured no-novel threshold or high-duplicate/no-qualified threshold after baseline coverage
- **THEN** the branch is recorded as saturated, unused allocation is made available for bounded reallocation, and the global run remains honest about completed coverage

### Requirement: Existing candidate truth pipeline remains authoritative
Autonomous discovery MUST route candidates through the existing normalization, deduplication, official-source verification, eligibility, scoring, portfolio comparison, auto-preparation, and delivery gates. Raw aggregators, posts, communities, and search results MUST remain untrusted leads.

#### Scenario: A duplicate or stale result is rediscovered
- **WHEN** a known opportunity or prior cycle is found again without material decision value
- **THEN** the canonical opportunity history and provenance are preserved while the discovery remains silent and the query/source metrics record the duplicate or stale outcome

### Requirement: Global cost controls are enforced by application state
The system MUST enforce per-branch, per-lens floor, global query/page/model/time/deep-evaluation/notification, adaptive-depth, source-check, and configurable daily caps in the deterministic application layer. Paid fallback MUST NOT activate silently.

#### Scenario: A global budget is exhausted
- **WHEN** a hard global or model budget is reached
- **THEN** affected branches stop safely, skipped lenses and the incomplete deep-discovery status are persisted, and no success or material delivery is fabricated
