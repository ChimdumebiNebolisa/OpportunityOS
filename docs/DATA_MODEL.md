# Data model

The database is an evidence ledger plus derived operational state.

| Area | Primary records | Invariant |
| --- | --- | --- |
| Provenance | `source_records`, `observations` | Every accepted value points to retained evidence. |
| Profile | `canonical_facts`, `review_items`, `human_resolutions` | Conflicts are visible; rebuilds preserve fact identity. |
| Opportunities | `opportunities`, `opportunity_requirements` | Annual cycles are distinct; source IDs and versions are explicit. |
| Decisions | `eligibility_checks`, `assessments`, `evaluations`, `decision_events` | Rules are deterministic and versioned; subjective inputs cite facts and sources. |
| Execution | `action_items`, `applications`, `application_artifacts` | READY requires a ≤24-hour official verification, complete reconciled requirements, current eligibility, future deadline, and intact grounded artifacts. |
| Automation | `scout_runs`, `discovery_runs`, `search_branches`, `profile_intelligence_runs` | V1/V2 scout compatibility, V3 global discovery state, and V3.1 bounded personal sweeps are durable. |
| Search memory | `query_strategies`, `source_registry` | Normalized query lineage, yield, source cadence, trust class, due checks, and disable reasons remain private and bounded. |
| Personal sources | `personal_source_sync_states`, `reconciliation_batches` | GitHub/Gmail/ChatGPT controls, capability state, cursors, high-water marks, material review batches, and delivery fingerprints remain private. |
| Operations | `audit_events`, `idempotency_keys` | Writes are auditable and retry-safe where exposed to MCP. |

`canonical_facts` are projections, not a replacement for observations. A human resolution records
the considered alternatives, chosen value or candidate, scope, resolver, and time. Newer evidence
reopens an `until_newer_evidence` resolution; a `fixed_interval` resolution controls projection only
inside its effective interval. Rebuilds reapply those rules to both entered values and selected
candidates.

SQLite uses foreign keys, WAL, immediate write-lock acquisition, and explicit transactions so local
check-then-insert duplicate and idempotency guards remain atomic. Alembic owns schema creation and
upgrade.
JSON columns hold typed values, predicates, evidence ID sets, input versions, and score breakdowns;
they never hold credentials.

V3.1 observations retain `source_event_at`, `subject_identity`, `assertion_kind`, and a
`content_fingerprint`. These fields preserve temporal meaning and prevent source replay from being
mistaken for a new user fact. Personal source rows are candidate inputs first; only the existing
profile application service can project canonical facts or create review items.

V3 `discovery_runs` link to bounded `search_branches`, and each branch may link to the existing
`scout_runs` row for compatibility with the Hermes scout interface. `query_strategies` are unique
within lens/family/template and preserve parent or seed lineage. `source_registry` stores canonical
domains rather than raw page bodies. Coverage reports contain counters and safe identifiers only;
raw search pages and source content remain in the private runtime cache.
