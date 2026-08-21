# Data model

The database is an evidence ledger plus derived operational state.

| Area | Primary records | Invariant |
| --- | --- | --- |
| Provenance | `source_records`, `observations` | Every accepted value points to retained evidence. |
| Profile | `canonical_facts`, `review_items`, `human_resolutions` | Conflicts are visible; rebuilds preserve fact identity. |
| Opportunities | `opportunities`, `opportunity_requirements` | Annual cycles are distinct; source IDs and versions are explicit. |
| Decisions | `eligibility_checks`, `assessments`, `evaluations`, `decision_events` | Rules are deterministic and versioned; subjective inputs cite facts and sources. |
| Execution | `action_items`, `applications`, `application_artifacts` | READY requires a ≤24-hour official verification, complete reconciled requirements, current eligibility, future deadline, and intact grounded artifacts. |
| Automation | `scout_runs` | Budgets, candidates, errors, delivery, and catch-up windows are durable. |
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
