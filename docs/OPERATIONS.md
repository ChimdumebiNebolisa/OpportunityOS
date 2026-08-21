# Operations

## Health and location

Run `opportunityos status` for data paths, database integrity, privacy audit, integration gates, and
recent scout state. `opportunityos doctor` fails only on blocking local checks; unconfigured Hermes,
Discord, OAuth, and GitHub remain `GATED` rather than being reported as failures or false successes.

## Backup and restore

`opportunityos backup` uses SQLite's online backup API, runs an integrity check, and writes a private
manifest containing schema version and SHA-256. Keep the database and manifest together.

Normal context startup checks the Alembic revision. Before applying any pending migration to an
existing schema, it creates and integrity-checks a uniquely named `pre-migration` database plus
manifest in the private backup directory. A fresh database is migrated directly to the current head.

Restore never overwrites an existing database:

```text
opportunityos restore PRIVATE_BACKUP.sqlite3 EMPTY_PRIVATE_DIRECTORY
```

The target must be empty and private. After restore, point `OPPORTUNITYOS_DATA_DIR` at the containing
private root only after checking `opportunityos doctor` against it.

## Export and retention

`opportunityos export` writes a private JSON snapshot of all tables. It is sensitive. Attachment
cleanup is scoped to ordinary files inside the private attachment directory:

```text
opportunityos purge --older-than-days 30
```

Packets, databases, backups, and exports are not purged by that command.

## Scouts

Each scout run persists query, page, deep-evaluation, model-call, duration, and notification caps.
The configured `daily_model_calls` cap is shared by all scout runs recorded during the current UTC
day. A candidate can appear in a digest only after the current evaluation, official source, open
status, future deadline, score, and confidence gates all pass; otherwise the run finishes quietly.
Delivered evaluation/version fingerprints are durable, so an unchanged strong candidate is quiet on
later runs and can reappear only after a materially changed, current evaluation passes the gate.

## Lifecycle

OpportunityOS never infers submission or outcome. `submitted` requires explicit confirmation and an
occurrence timestamp. Accepted/rejected outcomes require a user or authoritative imported evidence.
Every lifecycle transition is validated and audited.

Official-source reverification retrieves only the stored canonical URL. A changed content hash
supersedes the prior requirements, resets source completeness, returns the opportunity to
`REVIEW_REQUIRED`, and requires extraction plus evaluation before packet preparation can become
READY again.

## Release operations

Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Never diagnose a production/private dataset by
copying it into this repository; reproduce with synthetic data.
