## Purpose

Turns text, links, images, documents, and transcripts into one provenance-rich opportunity record without trusting imported instructions.

## ADDED Requirements

### Requirement: Common normalized intake
The system MUST accept supported text, URL, image, PDF, document, GitHub URL, post text, voice-derived transcript, and structured inputs through a common source, identification, verification, normalization, deduplication, evaluation, action, and persistence flow.

#### Scenario: Naked attachment
- **WHEN** Hermes submits a supported naked attachment without a conflicting intent
- **THEN** the system treats it as opportunity intake and returns a grounded status or an explicit verification/review requirement

### Requirement: Official-source priority
Aggregator, social, screenshot, and forwarded inputs MAY seed a lead, but deadline, eligibility, open status, and application link MUST come from official evidence when available.

#### Scenario: Screenshot-only lead
- **WHEN** an image identifies a program but contains no official URL
- **THEN** image facts remain candidates and the opportunity cannot receive a verified APPLY decision until an official source is attached

### Requirement: Safe source retrieval and file processing
The system MUST bound downloads, redirects, timeouts, document pages, retained bytes, and extraction work; validate MIME against extension; sanitize names; store by UUID; and never execute macros, scripts, archives, or imported commands.

#### Scenario: Misleading PDF extension
- **WHEN** a binary file with an incompatible MIME type is submitted as a PDF
- **THEN** the file is safely rejected without parsing, execution, traversal, or partial state

### Requirement: Deterministic deduplication
The system MUST normalize tracking URLs and use canonical URL plus organization, title, and cycle to merge duplicate sources while preserving separate annual cycles.

#### Scenario: Three representations of one opportunity
- **WHEN** a tracking URL, screenshot, and official page describe the same organization, title, and cycle
- **THEN** one opportunity retains three source records and produces no duplicate notification

### Requirement: Untrusted content isolation
Source content MUST be treated only as data; source instructions MUST NOT control tools, paths, credentials, rules, or canonical state, and detected injection attempts MUST create a security audit event.

#### Scenario: Malicious webpage
- **WHEN** a page asks the agent to read local files and mark the applicant eligible
- **THEN** those instructions are ignored, no local file is accessed, no eligibility mutation occurs, and a security event is recorded

