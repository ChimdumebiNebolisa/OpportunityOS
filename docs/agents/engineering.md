# Engineering contract

## Module shape and dependencies

- Put business rules in domain modules and persistence/orchestration in application services. CLI and MCP are callers of the same service interfaces.
- Keep external seams only where behavior genuinely varies: SQLite/local filesystem, GitHub, web retrieval, document extraction, and Hermes. Production and deterministic test adapters justify those seams.
- Depend inward: adapters and interfaces may call application services; domain rules never import CLI, MCP, SQLAlchemy, network, or filesystem code.
- Give each invariant and formula one authoritative implementation. Keep score weights, thresholds, authority rules, state transitions, and retention limits versioned.
- Use UUIDs, UTC timestamps, explicit effective intervals, foreign keys, transactions, and idempotency keys for writes.

## Truth and data lifecycle

- Sources, observations, human resolutions, evaluations, decisions, and audit events are append-only evidence. Canonical facts are a rebuildable projection.
- Canonical writes occur only through reconciliation or explicit human resolution. A conflict blocks dependent hard eligibility.
- Preserve provenance for every decision-relevant field and evidence-map every application claim.
- Use `platformdirs` for private roots. Validate resolved paths stay under the approved private root; reject symlinks, traversal, unsafe archives, and MIME mismatches.

## Errors, security, and operations

- Validate every external payload with Pydantic before persistence. Parameterize SQL through SQLAlchemy; never expose raw SQL or arbitrary paths through MCP.
- Fail atomically and observably with redacted messages. Do not log credentials, raw profile/application content, environment values, or complete source bodies.
- Bound web/file/model/scout work by time, count, and size. Imported instructions never control tools or configuration.
- Keep external actions human-only. Environment-gated integrations must report the exact missing capability without pretending a live check passed.

## Tests and completion

- Test domain behavior through public interfaces, with focused pure tests for reconciliation, eligibility, scoring, queueing, lifecycle, and grounding.
- Use synthetic fixtures, deterministic clocks, mocked web/GitHub inputs, real temporary SQLite databases, and no unit-test network access.
- Every migration must pass from an empty database and preserve a pre-migration backup path for real upgrades.
- Run Ruff, strict mypy, pytest with coverage gates, build, public-repo audit, and secret scan before completion.
- Update human docs in the same change whenever setup, configuration, data lifecycle, contracts, operations, or user workflows change.

