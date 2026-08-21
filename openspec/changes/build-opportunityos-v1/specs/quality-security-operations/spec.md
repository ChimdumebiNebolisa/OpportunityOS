## Purpose

Makes the public project reproducible, secure against its concrete local-agent threats, and verifiable with synthetic evidence on Windows and CI.

## ADDED Requirements

### Requirement: Repository privacy and secret defenses
The repository MUST ignore private/runtime files, scan staged and CI content for secrets, reject databases and private artifacts, audit tracked/untracked paths for personal data patterns, and contain only clearly synthetic fixtures.

#### Scenario: Deliberately staged private material
- **WHEN** a test sandbox stages a fake token and SQLite file
- **THEN** the public-repository audit fails and identifies both prohibited classes without printing the token

### Requirement: Threat controls
The system MUST enforce deny-by-default Discord configuration, untrusted-input isolation, schema validation, path containment, MIME checks, redacted logs, bounded work, transactional writes, and the absence of external-action tools.

#### Scenario: Prompt-injection fixture
- **WHEN** a malicious synthetic source requests secrets, commands, and eligibility override
- **THEN** security tests prove no command, secret read, canonical mutation, or external action occurs

### Requirement: Automated quality evidence
CI MUST validate the lockfile, formatting, lint, strict types, unit/integration/contract/e2e tests, migrations, coverage thresholds, build, secrets, privacy, and dependency vulnerabilities where practical.

#### Scenario: Pull request quality gate
- **WHEN** CI runs on a pull request or main
- **THEN** a failed required quality, security, migration, privacy, or coverage check blocks the workflow

### Requirement: Reproducible Windows bootstrap
The project MUST document and script non-administrator Windows setup, private initialization, MCP/skill registration assistance, doctor, and public audit while pausing for credentials and external authentication.

#### Scenario: Clean account without Hermes credentials
- **WHEN** setup runs on Windows with Git but no authenticated Hermes installation
- **THEN** local OpportunityOS installation and private initialization complete, and the user receives exact current external authentication steps

### Requirement: Local-only metrics and honest limitations
The system MUST collect operational and user-value counters locally without analytics upload and MUST distinguish locally verified behavior from credential-, network-, or clean-machine-gated checks.

#### Scenario: Verification report
- **WHEN** status or release evidence is generated
- **THEN** it lists environment-gated checks explicitly and never reports an unperformed live integration as passing

