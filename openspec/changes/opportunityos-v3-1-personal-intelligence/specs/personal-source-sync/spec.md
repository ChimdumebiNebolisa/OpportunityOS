## Purpose

Define safe, independently controlled, read-only personal-source adapters that turn authorized GitHub, Gmail, and ChatGPT evidence into bounded candidate observations without exposing unsupported capabilities or mutating external systems.

## ADDED Requirements

### Requirement: Personal sources have independent modes

The system MUST support GitHub and Gmail modes `disabled` and `continuous`, and ChatGPT modes `disabled`, `snapshot_only`, and `continuous`. Disabled sources MUST NOT be read.

#### Scenario: Disabled source
- **WHEN** a source is configured as disabled
- **THEN** a personal-intelligence run skips external reads for that source and reports the source as disabled

#### Scenario: ChatGPT snapshot-only mode
- **WHEN** ChatGPT is configured as snapshot-only
- **THEN** only explicitly supplied structured snapshots or files are processed and no background conversation read is attempted

### Requirement: Personal adapters are read-only

Personal-source adapters MUST NOT send, reply, label, archive, delete, modify, post, or change settings in Gmail, GitHub, ChatGPT, or any other external account.

#### Scenario: Gmail sweep
- **WHEN** the Gmail adapter inspects messages for profile evidence
- **THEN** it performs only read operations and returns bounded evidence locators and candidate proposals

### Requirement: GitHub evidence remains objective

The GitHub adapter MUST support incremental objective metadata such as repository creation, rename, archival state, descriptions, topics, releases, and merged pull requests when available. It MUST NOT infer expertise, prestige, impact, or research quality from metadata alone.

#### Scenario: New release
- **WHEN** a new repository release is observed after the stored cursor
- **THEN** the adapter emits an objective candidate observation with the repository URL and release locator

#### Scenario: Subjective claim
- **WHEN** GitHub metadata could suggest a skill or impact claim
- **THEN** the adapter does not create that subjective claim without separate supporting evidence

### Requirement: Gmail evidence is relevant and bounded

The Gmail adapter MUST prioritize configured material evidence classes, exclude spam and trash by default, inspect message bodies or attachments only within configured limits, and retain minimum necessary provenance rather than full unrelated message bodies.

#### Scenario: Relevant official result
- **WHEN** a read-only message from a program domain contains a clear acceptance or rejection
- **THEN** the adapter emits a candidate observation with message locator, sender/domain metadata, source timestamp, and bounded supporting evidence

#### Scenario: Irrelevant newsletter
- **WHEN** a message is marketing or unrelated newsletter content
- **THEN** the adapter emits no profile candidate and does not create review work

### Requirement: ChatGPT assertions are subject-isolated

ChatGPT continuous or snapshot evidence MUST distinguish user-authored direct assertions and corrections from assistant-authored claims, hypotheticals, quoted text, copied source material, brainstorming, and statements about third parties. Non-autobiographical content MUST NOT become canonical profile evidence.

#### Scenario: User correction
- **WHEN** a user-authored message explicitly corrects an earlier graduation date
- **THEN** the system preserves both observations and submits the newer correction for deterministic reconciliation

#### Scenario: Third-party or hypothetical statement
- **WHEN** a conversation contains a hypothetical plan or a statement about another person
- **THEN** the system suppresses it from personal candidate observations

### Requirement: Source evidence is private and provenance-backed

Source cursors, sync analytics, bounded evidence, fingerprints, and personal-source content MUST remain in private runtime state. Candidate observations MUST retain a source locator, source timestamp when available, observed timestamp, source type, and extraction metadata.

#### Scenario: Public repository audit
- **WHEN** the public-repository audit scans the repository
- **THEN** it finds no personal message bodies, ChatGPT conversation dumps, Gmail data, cursors, or source credentials
