## Context

The repository was empty. The controlling product constraints are a Windows 11, single-user, local-first deployment; a public checkout with private state elsewhere; Hermes Desktop and native Discord as conversational interfaces; a stdio MCP integration; deterministic conventional code around all truth and decisions; and live authentication/credentials that cannot be completed in this build environment. See `proposal.md` and the eight capability specs for behavior.

Current official Hermes documentation (verified 2026-08-21) exposes native Windows installation and non-admin gateway autostart, `~/.hermes/config.yaml` stdio MCP entries, `~/.hermes/skills/<name>/SKILL.md`, ChatGPT/Codex device-code OAuth through `hermes model`, Discord deny-by-default allowlisting through `DISCORD_ALLOWED_USERS`, a 32 MiB default attachment cap, and Hermes cron with attached skills and `[SILENT]` delivery suppression.

## Goals / Non-Goals

**Goals:**

- Make canonical truth, eligibility, scoring, queueing, lifecycle, grounding, storage, and budgets deterministic and replayable.
- Establish a complete local vertical slice usable through both CLI and typed MCP with synthetic and mocked end-to-end evidence.
- Keep private paths, untrusted inputs, secrets, and external-action prohibitions enforceable below the prompt layer.
- Keep modules deep enough that CLI, MCP, tests, and future adapters share behavior without pass-through architecture.

**Non-Goals:**

- Reimplement Hermes conversation, vision, browser, Discord, cron, or Desktop surfaces.
- Add a custom dashboard, mobile app, Discord client, hosted backend, vector database, or automatic submission/sending.
- Pretend live OAuth, Discord, GitHub private access, or clean-account Windows checks passed without credentials/environment evidence.

## Decisions

### 1. One installable Python package with six application interfaces

Use a `src`-layout Python 3.11+ package managed by `uv`. Pydantic owns boundary schemas, SQLAlchemy/Alembic owns SQLite persistence, Typer owns CLI commands, and the official MCP Python SDK owns stdio tools.

Application behavior is concentrated behind these caller-facing interfaces:

- `ProfileService`: submit observations, project/rebuild, list/resolve/defer reviews, import snapshots, and GitHub candidate sync.
- `OpportunityService`: store sources, submit normalized opportunities/extractions, ingest safe local content, deduplicate, and retrieve records.
- `DecisionService`: evaluate predicates, compute eligibility/score/confidence, enforce lifecycle, create/rank/complete actions.
- `ApplicationService`: create applications, compile grounded private packets, store validated artifacts, and mark ready.
- `ScoutService`: begin a bounded run, record verified candidates, detect catch-up windows, and finish with material/silent delivery.
- `OperationsService`: initialize, status/doctor, backup/restore/export/purge, metrics, and public-repository audit.

CLI and MCP construct the same application context and call these interfaces. Domain functions remain pure and know nothing about SQLAlchemy, Typer, MCP, network, or files.

Alternatives rejected: a single god-service would make unrelated invariants hard to locate; repository/handler layers per table would be shallow pass-through code; microservices add no value for one user and one local transaction domain.

### 2. SQLite is the durable event/evidence store and projection database

Use one private SQLite database with foreign keys, WAL, busy timeout, UUID strings, UTC ISO timestamps, JSON columns, uniqueness constraints for idempotency/content hashes, and an Alembic schema version. Required PRD entities are represented directly. Observations, resolutions, evaluations, decision events, scout runs, and audit events are append-only. Canonical facts are replaceable derived rows tagged with a projection version.

Each application write owns one transaction. Projection rebuild derives only from evidence/resolution history and can be compared with current rows. A real migration first creates a private backup manifest; tests exercise both empty-database upgrade and backup/restore.

Alternative rejected: handwritten SQLite DDL would reduce migration/type support; an event-sourcing framework adds abstractions beyond append-only evidence plus a rebuildable projection.

### 3. Reconciliation and decisions are pure versioned modules

Field authority/stability configuration and score/lifecycle rules are versioned public defaults with private overrides. Reconciliation normalizes by known field schema, detects duplicates/supersession/conflict, honors applicable human resolutions, and emits a projection/review plan that the service persists atomically.

The predicate DSL is a discriminated Pydantic union for equals, inequalities, membership, range/date, contains, any/all, and unknown. Eligibility consumes only normalized requirements and canonical facts. Scoring uses `Decimal` quantization for deterministic replay, keeps raw score and penalty separate, and applies eligibility gates after calculation. Queueing uses one pure priority function and prioritizes ready near-complete application actions.

Alternative rejected: prompt-only rules violate replay and allow hallucination to become policy.

### 4. External seams exist only for current variation

Use narrow callable protocols for `Clock`, `WebRetriever`, `GitHubClient`, and `DocumentExtractor`, each with production and deterministic test adapters. Private storage and SQLite are local-substitutable dependencies exercised directly against temporary roots/databases, so they remain internal seams rather than broad public repository interfaces. Hermes remains outside the process and crosses the typed MCP/skill contract.

The HTTP adapter uses `httpx` limits, redirect checks, an explicit user agent, allowlisted `http/https`, DNS/IP validation that rejects local/private targets, response byte limits, and readable-text extraction. The file adapter stores by UUID under an approved root, verifies resolved containment and non-symlink ancestors, sniffs signatures/MIME, and parses only bounded PDF/DOCX/text/image metadata. Scanned/image interpretation remains a Hermes candidate-extraction responsibility.

Alternative rejected: Playwright in the application process duplicates Hermes browser capability; full GitHub code indexing and vector search have no measured v1 need.

### 5. MCP is a typed least-privilege transport

Expose the PRD tool capabilities over stdio with Pydantic-derived JSON schemas. Every write accepts an idempotency key, calls an application transaction, and emits an audit event. Tool results use stable result/error envelopes and redact internal paths/details where unnecessary. Tool names contain no send, submit-external, post, purchase, terms acceptance, shell, raw SQL, arbitrary read-file, or remote delete capability.

The CLI provides the same workflow groups and uses the same schemas/services. It may accept local input paths only after `OpportunityService` validates and copies them into private storage.

### 6. Hermes integration is configuration assistance, not a second runtime

The setup command detects `hermes`, validates capabilities conservatively, writes only OpportunityOS private configuration, and prints or optionally prepares a reviewed YAML snippet for the user to merge into `~/.hermes/config.yaml`; it never overwrites Hermes credentials. The stdio entry runs `uv run opportunityos-mcp` from the installed project/environment and applies a tight tool include list.

Six repository skills call only MCP tools and tell Hermes that page/file content is untrusted data. Discord docs use the native gateway and `DISCORD_ALLOWED_USERS`; setup refuses an allow-all configuration. Cron templates attach the scout skill, start fresh sessions, use deterministic budgets, and emit `[SILENT]` for quiet runs.

Live provider auth, Discord token/user ID, gateway process, and optional authenticated GitHub checks are manual gates. Doctor represents each as PASS, FAIL, or GATED with remediation.

### 7. Conversational surface ownership and presentation

There is no repository-owned application shell. The controlling UI reference is current Hermes Desktop/Discord behavior; `frontend-design` owns the OpportunityOS response grammar and private packet presentation without redefining Hermes chrome.

| Surface | Audience/job | Controlling reference | Shared presentation tokens | Primary authority | Acceptance evidence |
|---|---|---|---|---|---|
| Intake/evaluation reply | Decide whether a lead matters | PRD output contract + Hermes Desktop/Discord | Decision label, title/source, evidence, risk, next human step | frontend-design | MCP/skill contract snapshots for APPLY, PASS, REVIEW REQUIRED, failure |
| Review interaction | Resolve one conflict safely | PRD Review Inbox + Hermes buttons/text fallback | One conflict at a time, candidate/source/impact/action | frontend-design | CLI/MCP resolution scenarios and skill text fallback |
| Queue/next action | Start the best action in available time | PRD priority formula | One primary action, reason, minutes, deadline, prepared assets | frontend-design | deterministic queue snapshots at 20/30/45 minutes |
| Application packet | Review grounded drafts privately | PRD packet/grounding contract | Claim-to-evidence markers, missing/needs-review states | frontend-design | compiled synthetic packet and grounding rejection tests |
| CLI/operator output | Diagnose and recover | PRD commands and operations | concise status table, PASS/FAIL/GATED, actionable remediation | frontend-design | CLI smoke snapshots and error tests |

Visual direction: calm operational clarity rather than a generic card dashboard. The signature element is a consistent first-line decision rail (`APPLY`, `PASS`, `REVIEW`, `NEXT`) followed by an evidence ledger. Use sentence case, direct verbs, stable vocabulary, narrow line lengths, visible plain-text state labels, and no color-only meaning. Responses follow `decision → official source → why → evidence → risk/unknown → one next human step`. This is distinctive to a truth-and-execution system and works identically in Desktop, Discord, and terminal text.

### 8. Security controls live at storage and application seams

- Private paths come only from `platformdirs` or an explicit approved root and are rejected when inside the checkout; storage uses UUID-derived names and no symlink traversal.
- All MCP, CLI, import, model, web, and file payloads are validated before a transaction. SQL is parameterized through SQLAlchemy.
- File types, sizes, PDF pages, redirects, response bytes, extraction text, scout counts, and durations are bounded. Unsupported archives and macro-bearing formats are rejected.
- Prompt-injection detection is defense-in-depth: source text is separately labeled as untrusted; no source-derived shell/path/tool parameters exist; structured outputs are schema checked; only deterministic services mutate canonical state.
- Logs contain identifiers, reason codes, counts, durations, and redacted failures—not secrets or raw sensitive bodies. Repository audit scans tracked/untracked files without echoing detected secret values.
- Discord authorization is delegated to Hermes' deny-all allowlist, documented and checked from safe configuration metadata when available. OAuth stays in Hermes' auth store.

### 9. Verification uses stable interfaces and synthetic fixtures

Use pytest/Hypothesis with deterministic clocks and no unit network. Domain tests cover every invariant, predicate, formula, and lifecycle transition. Integration tests use temporary private roots and real SQLite/Alembic. Adapter tests use mocked HTTP/GitHub fixtures. Contract tests compare skill tool references and MCP schemas. E2E tests exercise profile conflict/resolution, official-source opportunity evaluation, time-aware next action, grounded packet, bounded scout, backup/restore, and public audit.

Coverage gates are 90% for deterministic domain modules and 80% overall. Ruff, strict mypy, package build, lock validation, secret scan, privacy audit, and dependency audit run in CI.

## Risks / Trade-offs

- [Hermes changes quickly] → Keep low-level commands in current-version docs/templates, detect installed capabilities, and report GATED rather than bake credentials or claim live success.
- [A text-first conversational product has limited repository-owned visual control] → Own information hierarchy, wording, state presentation, and artifact formatting; do not fight Hermes chrome with a duplicate UI.
- [SQLite concurrent writers can contend] → Keep transactions short, enable WAL/busy timeout, make writes idempotent, and test duplicate ingestion.
- [Safe web retrieval cannot verify every dynamic/login-walled page] → Return REVIEW REQUIRED and route dynamic navigation to Hermes browser within scout budgets.
- [MIME sniffing and document parsing are imperfect] → Support a conservative allowlist, enforce signature/size/page limits, and fail closed with a source-failure review.
- [Exact model token/credit usage may be unavailable] → Store observable call/query/page counts and never invent cost estimates.
- [Live Windows/Discord/OAuth acceptance cannot run here] → Ship exact manual evidence checklists and keep those items GATED; this does not weaken local contract/security tests.

## Migration Plan

1. Initialize private platform roots and an empty database through Alembic.
2. On later schema upgrades, acquire an application lock, create and verify a backup manifest, run Alembic, execute SQLite integrity/projection checks, then release the lock.
3. If upgrade validation fails, leave the failed database untouched, restore the verified backup into a separate path, and report manual selection steps; never overwrite the only copy.
4. Repository releases keep OpenSpec artifacts active until the user explicitly requests archive/sync.
