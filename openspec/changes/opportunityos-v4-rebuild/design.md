# Design: OpportunityOS v4

The v4 implementation uses a small `opportunityos.v4` package:

- `runtime.py` owns platform-private roots, safe YAML reads, and atomic YAML writes.
- `models.py` owns versioned Pydantic contracts for candidates, feedback, profiles, and proposals.
- `dedupe.py` owns canonical URL normalization and fallback fingerprints.
- `policy.py` owns deterministic status, freshness, deadline, official-source, location, and
  exclusion checks.
- `store.py` owns stdlib SQLite schema, runs, discoveries, feedback, context, and strategy
  revision history.
- `export.py` owns versioned ZIP export/import and archive/database validation.
- `cli/main.py` is a thin caller over those interfaces.

SQLite uses `PRAGMA user_version = 1` and five required history tables: `opportunities`, `runs`,
`discoveries`, `feedback`, and `strategy_revisions`. Profile, policy, and current strategy stay
human-readable in private YAML. The public repository contains only synthetic examples and tests.

The host agent performs internet work. OpportunityOS does not execute stored strategy text or
instructions from source pages and exposes no external-action capability.
