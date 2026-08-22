## 1. Repository and private runtime

- [x] 1.1 Create the Python package, pinned dependency groups, lockfile, license, ignore/pre-commit rules, configuration defaults, and CI skeleton; verify local dependency sync and package build succeed.
- [x] 1.2 Implement private platform roots, path containment, structured redacted logging, and public-repository audit; verify isolation, traversal/symlink rejection, fake-secret, and staged-database tests pass.
- [x] 1.3 Implement SQLAlchemy models, SQLite pragmas, Alembic migration, and transactional application context; verify empty migration, foreign keys, WAL, integrity check, and rollback tests pass.

## 2. Profile truth and review

- [x] 2.1 Implement Pydantic evidence/profile schemas, field authority/stability rules, and observation persistence; verify provenance and append-only tests pass.
- [x] 2.2 Implement deterministic reconciliation, canonical projections, supersession, conflict deduplication, and audit events; verify F-01, F-02, deterministic rebuild, and Hypothesis properties pass.
- [x] 2.3 Implement review listing, deferral, human resolution, dependency impact, and reevaluation triggers; verify CLI/service conflict-resolution integration tests pass.
- [x] 2.4 Implement structured ChatGPT snapshot and conservative GitHub adapters; verify candidate-only import, GitHub inference boundary, public fallback, and mocked failure tests pass.

## 3. Opportunity intake and evidence

- [x] 3.1 Implement source/opportunity/requirement schemas, URL normalization, semantic keys, versions, and source persistence; verify annual-cycle and duplicate-source tests pass.
- [x] 3.2 Implement safe file storage and bounded PDF, DOCX, text, and image-metadata extraction; verify MIME mismatch, traversal, page/size limit, and scanned-fallback contract tests pass.
- [x] 3.3 Implement safe HTTP retrieval/readable extraction and official-source reconciliation contracts; verify tracking redirects, SSRF/private-address rejection, login-wall failure, freshness, and prompt-injection tests pass.
- [x] 3.4 Implement the common service intake path and model-output validation/repair failure handling; verify synthetic URL, text, PDF, screenshot-candidate, duplicate-concurrency, and invalid-JSON flows pass.

## 4. Deterministic decisions and execution queue

- [x] 4.1 Implement the versioned predicate DSL and eligibility engine; verify all operators, hard fail, hard unknown/conflict, ambiguity, and explanation tests pass.
- [x] 4.2 Implement evidence-linked assessments, weighted scoring, effort penalty, confidence, decisions, and versioned evaluation persistence; verify replay and weight-change tests pass.
- [x] 4.3 Implement lifecycle transition enforcement and decision events; verify every allowed/denied transition and atomic-failure test passes.
- [x] 4.4 Implement action creation, urgency/readiness/time-fit, global ranking, and one-action selection; verify expired exclusion, 20/30/45-minute selection, and near-complete application priority pass.

## 5. Application preparation and operations

- [x] 5.1 Implement application creation, evidence-map validation, grounded artifact storage, packet compilation, reverification, and READY enforcement; verify supported and unsupported claim packet tests pass.
- [x] 5.2 Implement backup manifests, restore, JSON export, scoped purge, metrics, setup, status, and doctor; verify backup/restore equivalence, path safety, integrity, and GATED integration output tests pass.

## 6. Scouts, CLI, MCP, and Hermes

- [x] 6.1 Implement category scout budgets, catch-up windows, candidate recording, material-change detection, scholarship gates, and quiet finish behavior; verify F-20, cap-stop, mocked scholarship, and quiet-run tests pass.
- [x] 6.2 Implement all required Typer command groups against application interfaces; verify CLI help and end-to-end synthetic profile/intake/review/queue/prepare/backup workflows pass.
- [x] 6.3 Implement the typed stdio MCP server with PRD tool capabilities, idempotent writes, safe envelopes, and no external actions; verify MCP integration and schema snapshot tests pass.
- [x] 6.4 Author and contract-test six Hermes skills plus reviewed MCP/cron configuration templates; verify every referenced MCP tool exists and injection/failure/external-action rules are present.

## 7. Documentation, setup, and release hardening

- [x] 7.1 Add Windows/cross-platform setup scripts, synthetic demo seeding, and current Hermes registration assistance; verify non-admin local setup and private initialization in an isolated directory.
- [x] 7.2 Complete README, architecture/data/scoring, Hermes/Discord/profile, security/privacy/threat, operations/troubleshooting/compatibility/release documentation and copy the PRD; verify links, commands, environment names, and implemented behavior are synchronized.
- [x] 7.3 Run Ruff format/lint, strict mypy, pytest with domain/overall coverage gates, migration tests, package build, lock check, dependency audit, Gitleaks, and public-repository audit; fix all failures and record exact environment-gated live checks.
- [x] 7.4 Render representative conversational/CLI/packet states at desktop and narrow widths, inspect hierarchy/accessibility/copy, and verify corrected snapshots retain decision-evidence-risk-next-step order.
- [x] 7.5 Run final Vibe Security and Code Review Expert gates, adjudicate findings, exercise the highest-risk adversarial workflow, rerun affected checks, and verify no accepted Critical/High or P0/P1 remains.
