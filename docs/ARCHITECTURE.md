# OpportunityOS v4 architecture

OpportunityOS is the durable state and deterministic protocol layer between a user and an
external AI agent.

```text
User -> agent runtime -> OpportunityOS CLI -> private YAML + SQLite
                    \-> search and browsing tools
```

The agent owns conversation, intent interpretation, web search, browsing, extraction, verification
research, query generation, and user-facing explanation. OpportunityOS owns four durable concepts:

1. **Profile**  -  flexible user context in `profile.yaml`.
2. **Policy**  -  hard, deterministic search constraints in `policy.yaml`.
3. **Strategy**  -  transparent, revisioned search guidance in `strategy.yaml`.
4. **History**  -  SQLite records in `state.db`.

## Runtime boundary

`RuntimePaths` resolves a private application-data directory through `platformdirs`, with
`OPPORTUNITYOS_DATA_DIR` available for tests and portable installations. The root must not be inside
the repository and cannot be reached through a symlink or Windows junction.

The public checkout contains schemas, generic defaults, reference guidance, and synthetic tests.
It must not contain a real profile, policy, strategy, history database, export, or secret.

## Deterministic core

The v4 core uses Pydantic for external contracts, `sqlite3` for history, YAML for human-readable
profile/policy/strategy state, and the standard library for URL normalization and ZIP portability.
There is no web retrieval, document ingestion, application management, scheduler, dashboard, MCP
requirement, or custom agent loop.

Candidate identity is the normalized source URL, with a fallback SHA-256 fingerprint over normalized
organization, title, category, and cycle/year metadata. Tracking parameters and URL fragments are
removed. Previously seen records are suppressed unless a material change is observed.

Policy evaluates status, deadlines, official verification, freshness, location, and configured
exclusions. Unknown values stay unknown and follow the configured `allow`, `allow_with_warning`, or
`reject` behavior. Strategy updates cannot mutate profile, policy, privacy, or permission fields.

## Search protocol

```text
context(category)
  -> run start
  -> agent searches and verifies
  -> candidate check
  -> candidate record
  -> run finish
  -> feedback
  -> optional strategy proposal and revision
```

Agent-facing JSON responses include `schema_version: 1`. Accepted strategy changes create a new
SQLite revision with reason, evidence, agent/model metadata, diff, and the resulting strategy state.
Rollback creates a new revision that restores the selected prior state.

## Portability

`opportunityos export` writes a versioned ZIP containing `profile.yaml`, `policy.yaml`,
`strategy.yaml`, and `state.db`. Import validates every member and the database schema in a staging
directory before replacing the private state files. No pickle or executable content is accepted.
