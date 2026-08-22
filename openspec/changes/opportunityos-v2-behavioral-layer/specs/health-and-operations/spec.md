## Purpose

Makes local automation observable and recoverable through private backups, health state, operational controls, and migration-safe status without introducing a second scheduler or external-action capability.

## ADDED Requirements

### Requirement: Automatic backups are private, verified, and bounded
The system MUST create an automatic private backup when the database has changed since the last backup or the weekly safety interval has elapsed, reuse the existing SQLite backup path, verify integrity and checksum, write a minimal manifest, and apply configurable retention outside the repository.

#### Scenario: Automatic backup succeeds
- **WHEN** the automatic-backup trigger is due
- **THEN** a private integrity-checked backup and checksum manifest are created, retained according to policy, and success remains silent

#### Scenario: Automatic backup fails
- **WHEN** backup creation or verification fails
- **THEN** the failure is persisted with an actionable health/notification state and no success is reported

### Requirement: Health checks report actionable runtime state
Health status MUST cover the local database, last successful scouts, backup freshness, scheduler presence, Hermes availability where observable, and repeated operational failures without inspecting or printing credential values.

#### Scenario: Stale scout health
- **WHEN** a category has exceeded its configured maximum silence interval without a successful run
- **THEN** health is unhealthy with an actionable detail code and a concise notification candidate

#### Scenario: Recovery
- **WHEN** a previously failing component passes a later check
- **THEN** its consecutive failure state clears and at most one concise recovery event is eligible for delivery

### Requirement: Automation controls are explicit and local
The system MUST expose local controls to list/pause scouts, pause all proactive automation, disable auto-preparation, disable each brief class, disable reminders, inspect history/status, run one scout, and request or record user-approved lifecycle actions. Controls MUST be idempotent and MUST NOT alter external accounts.

#### Scenario: Pause all automation
- **WHEN** the user pauses all proactive automation
- **THEN** scheduled behavioral operations become no-ops with an inspectable paused state while explicit manual reads and approval-gated lifecycle updates remain available

### Requirement: V2 migration preserves existing private state
The V2 schema migration MUST create a pre-migration backup and integrity check before upgrading, preserve all V1 profile/opportunity/evaluation/action/application/scout/audit records, and leave the original database recoverable if migration fails.

#### Scenario: Migration from V1 database
- **WHEN** a V1 database is upgraded
- **THEN** all existing records remain readable, new behavior tables are available, and the pre-migration backup remains outside the repository
