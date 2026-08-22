# Operations

## Health and location

Run `opportunityos status` for data paths, database integrity, privacy audit, integration gates, and
recent category-scout and V3 global-discovery state. Hermes discovery checks PATH first and then its documented per-user installation
locations, so a shell opened before the installer updated PATH still reports the installed runtime.
The status separates Hermes installation, Codex OAuth, OpportunityOS MCP configuration, private
Discord configuration, gateway process state, and an external live round trip. `opportunityos
doctor` fails only on blocking local checks; unverified external states remain `GATED` rather than
being reported as failures or false successes.

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

V2 category scout calls remain supported and keep their existing budgets and delivery gates. V3
keeps Hermes cron as the scheduler for two global cycles, defaulting to 06:00 and 18:00 in the
configured local timezone. Start a cycle with `opportunityos discovery begin`; record bounded query
and source outcomes with the matching discovery commands; inspect `discovery coverage RUN_ID` when
needed; and finish with explicit completed/skipped lenses. A missed cycle produces one bounded
catch-up origin rather than replaying every missed occurrence. Use `discovery strategies`,
`discovery sources --due-only`, and `discovery status` for private recovery inspection.

Discovery metrics, branch mechanics, source checks, and saturation are silent by default. Scheduled
skills return `[SILENT]` when no material item clears the existing candidate and delivery gates.

## Personal intelligence

V3.1 runs a bounded personal-intelligence sweep before morning discovery. Hermes owns the default
05:00 local schedule; OpportunityOS owns the run, source cursors, provenance, candidate-to-canonical
reconciliation, review batching, and downstream reevaluation. Inspect it with:

```text
opportunityos profile intelligence status
opportunityos profile source capabilities
opportunityos profile source list
opportunityos profile intelligence review-batches
```

GitHub, Gmail, and ChatGPT controls are independent. GitHub and Gmail use `disabled` or
`continuous`; ChatGPT additionally supports `snapshot_only`. Source adapters are read-only and
advance a cursor only after a successful bounded batch. A failed or unsupported source keeps its
cursor and is surfaced as `GATED`/blocked. Imported or model-derived content is untrusted: third-
party, hypothetical, quoted, assistant-summary, and other suppressed assertions remain candidate
evidence without mutating canonical profile truth. Material differences create review items;
exact agreement is silent. Change a source control explicitly, for example:

```text
opportunityos profile source set gmail --enabled false
opportunityos profile source set chatgpt --mode snapshot_only --enabled true
```

The scheduled skill returns `[SILENT]` when no material reconciliation or source-health change needs
delivery. It must not claim Gmail or continuous ChatGPT synchronization when the corresponding
provider capability is unavailable.

## Execution, reminders, and briefs

Use `opportunityos execution-next --minutes 30` for one primary action and
`opportunityos execution-risk --minutes 30` for high-value unfinished work that may need a
reminder. Reminders respect `notifications.daily_cap`, quiet hours, snooze, stop, and material
fingerprints. `opportunityos brief daily`, `brief evening`, and `brief weekly` return silent results
when there is nothing material to deliver. Weekly strategy output is advisory and never changes
scoring automatically.

`opportunityos followup-due` checks only explicitly submitted opportunities. A follow-up draft is
private and is never sent automatically. Disable controls locally with
`opportunityos automation-control <key> false`; list effective values with
`opportunityos automation-controls`.

## Automatic preparation and health

`opportunityos auto-prepare-gate OPPORTUNITY_ID` records the deterministic V2 gate. Automatic
execution requires a current high-confidence APPLY opportunity and reuses the grounded V1 packet
compiler; it stops at private artifacts. `opportunityos health` reports database, category-scout, global-discovery, configured-schedule, and
backup freshness without inspecting credentials. `opportunityos backup-auto` reuses the verified
SQLite backup path and applies bounded private retention.

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
