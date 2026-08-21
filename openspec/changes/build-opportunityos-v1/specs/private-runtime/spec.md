## Purpose

Keeps all personal state outside the public checkout while providing durable local storage, configuration, recovery, and health evidence.

## ADDED Requirements

### Requirement: Private runtime boundary
The system MUST resolve private data and configuration roots from platform conventions by default and MUST refuse a configured runtime path that resolves inside the repository, through a symlink, or outside an approved root.

#### Scenario: Normal workflow isolation
- **WHEN** any normal workflow stores a database, source, attachment, log, backup, or application artifact
- **THEN** the artifact is written under the private runtime root and no private runtime file appears in the checkout

### Requirement: Configuration precedence and secrecy
The system MUST apply command options, private configuration, secret environment variables, and public defaults in descending precedence and MUST keep secret values out of public examples, logs, status output, and repository files.

#### Scenario: Private override
- **WHEN** a private configuration value overrides a public default
- **THEN** the effective non-secret setting is used and the private file remains outside the repository

### Requirement: Transactional durable storage
The system MUST enforce foreign keys, transactional writes, an appropriate busy timeout, schema versioning, idempotent write keys, and append-only evidence/audit history.

#### Scenario: Failed mutation
- **WHEN** a write fails after validation but before completion
- **THEN** the transaction rolls back without partial canonical state and a redacted actionable error is returned

### Requirement: Backup, restore, export, and purge
The system MUST create hashed private backups, validate them before restore, export portable JSON, back up before real migrations, and provide scoped purge operations.

#### Scenario: Restore into a clean root
- **WHEN** a valid backup is restored into an empty approved private directory
- **THEN** canonical profile state and stored evaluations reproduce the backed-up state

### Requirement: Operational health
The system MUST report database integrity, private-path safety, backups, integrations, gateway/scout availability, urgent reviews, and public-repository audit state without exposing secrets.

#### Scenario: Hermes is unavailable
- **WHEN** Hermes is not installed or the gateway cannot be checked
- **THEN** doctor reports an environment-gated item with exact remediation and does not claim continuous phone or scout availability

