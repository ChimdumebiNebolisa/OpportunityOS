## Purpose

Extend the existing append-only profile ledger so repeated source evidence remains quiet, material uncertainty reaches review, historical facts are preserved, and accepted changes can trigger bounded downstream reevaluation.

## ADDED Requirements

### Requirement: All personal evidence uses the existing candidate pipeline

GitHub, Gmail, and ChatGPT evidence MUST enter the existing source-record, observation, deterministic reconciliation, and canonical projection pipeline. No personal adapter may write canonical facts directly.

#### Scenario: Candidate-before-canonical
- **WHEN** a personal adapter extracts a new profile claim
- **THEN** the claim is persisted as a provenance-backed candidate observation before any canonical projection change

### Requirement: Candidate observations are fingerprinted and deduplicated

The system MUST fingerprint source records and normalized field/value/effective-time observations. Exact duplicate support MUST remain silent and MUST NOT create repeated review work.

#### Scenario: Exact agreement
- **WHEN** a new source repeats an already accepted fact without a material temporal or authority change
- **THEN** the system records supporting provenance as appropriate and creates no new reconciliation item

#### Scenario: Same evidence replay
- **WHEN** the same source record is presented again with the same content fingerprint
- **THEN** the system does not create a second source record or duplicate candidate observation

### Requirement: Materiality controls review creation

The system MUST create or update review work for material contradictions, ambiguous subject attribution, materially newer high-impact facts, major goal or constraint changes, and credible cross-source disagreement. It MUST suppress trivial restatements, minor GitHub noise, irrelevant content, and repeated assistant summaries.

#### Scenario: Material contradiction
- **WHEN** two credible overlapping observations disagree on a high-impact field
- **THEN** the canonical field remains conflicted and one open review item references the candidate identifiers

#### Scenario: Low-value noise
- **WHEN** a source produces a minor restatement below the configured materiality threshold
- **THEN** the observation may remain historical but no user review item is created

### Requirement: Historical and temporal semantics are preserved

The system MUST retain older observations and source timestamps when a newer fact supersedes current projection. Plans, hypotheticals, stale records, and corrections MUST NOT be silently treated as current reality without deterministic reconciliation.

#### Scenario: Newer current fact
- **WHEN** a source provides a materially newer fact with sufficient authority
- **THEN** the newer fact may supersede the current projection while the older observation remains queryable

#### Scenario: Old source discovered late
- **WHEN** an initial bootstrap finds a source record older than the current projection
- **THEN** the system preserves its historical timestamp and does not automatically treat retrieval time as the fact's effective time

### Requirement: Accepted material changes trigger bounded propagation

When canonical profile state materially changes through safe authority or explicit resolution, the system MUST identify dependent opportunities and expose a bounded reevaluation request. Unresolved review items MUST NOT mutate canonical state or invalidate decisions by themselves.

#### Scenario: Accepted change with dependents
- **WHEN** a graduation date or other field used by opportunity requirements is accepted
- **THEN** dependent evaluations can be invalidated and reevaluated within the configured limit, and search/profile-gap inputs are refreshable

#### Scenario: Unresolved conflict
- **WHEN** a conflicting candidate remains open for review
- **THEN** the canonical conflict state remains authoritative and no downstream change is applied from the unresolved candidate
