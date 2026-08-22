## Why

OpportunityOS is needed to turn a fast-growing stream of scholarships, programs, grants, and competitions into a small, evidence-backed execution queue without letting model inference corrupt profile truth or private data leak into a public repository.

## What Changes

- Add a reproducible Python 3.11+ local-first application with private platform-specific storage, SQLite persistence, migrations, audit history, backup, restore, export, purge, doctor, and public-repository safety checks.
- Add an append-only profile evidence ledger, deterministic canonical projection, conflict detection, review inbox, human resolution, ChatGPT snapshot import, and conservative GitHub evidence sync.
- Add one normalized opportunity pipeline for text, URLs, images, PDFs, documents, and voice-derived transcripts, with official-source priority, safe file handling, source provenance, deduplication, and prompt-injection isolation.
- Add deterministic requirement predicates, eligibility, reproducible scoring, confidence, lifecycle rules, the global action queue, and time-aware next-action selection.
- Add grounded private application packets whose claims must map to accepted profile evidence and which never submit or send externally.
- Add a typed stdio MCP server, six project-owned Hermes skills, current-version setup guidance for Hermes Desktop, ChatGPT/Codex OAuth, native Discord allowlisting/attachments, and Hermes cron.
- Add bounded category scouts with catch-up windows and quiet-digest behavior, plus complete synthetic tests, CI, security/privacy controls, and operator documentation.

## Capabilities

### New Capabilities

- `private-runtime`: Private paths, configuration, SQLite lifecycle, audit, backup/restore/export/purge, health checks, and public-repository isolation.
- `profile-ledger`: Provenance-bearing observations, canonical projection, conflicts, review, human resolution, imports, and rebuildability.
- `opportunity-intake`: Safe multi-format intake, official-source evidence, normalized opportunities and requirements, and deterministic deduplication.
- `deterministic-decisions`: Requirement DSL, eligibility, scoring, confidence, priority queue, lifecycle, and time-aware actions.
- `application-packets`: Evidence-grounded private preparation packets and readiness enforcement without external submission.
- `hermes-integration`: Typed MCP contracts, CLI parity, Hermes skills, Desktop workflows, Discord gateway configuration, and Codex OAuth setup.
- `bounded-scouts`: Category discovery runs, budgets, catch-up behavior, deduplication, scholarship gates, and quiet digests.
- `quality-security-operations`: Security controls, synthetic fixtures, CI quality gates, Windows setup, operational documentation, and local-only metrics.

### Modified Capabilities

None.

## Impact

The change creates the entire public repository: Python package and lockfile, Alembic schema, CLI and MCP entry points, Hermes skills, private storage conventions, adapters, tests, Windows/cross-platform setup scripts, CI workflows, and all required user/security/operations documentation. Live Hermes OAuth, Discord, and public GitHub credential checks remain explicit environment-gated verification steps; their local contracts, validation, and failure modes are testable without credentials.
