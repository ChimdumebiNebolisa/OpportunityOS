# OpportunityOS

**OpportunityOS is a model-agnostic, self-learning framework for discovering and tracking opportunities across AI models.**

It gives AI agents portable access to a user’s profile, hard search constraints, learned search
strategies, and opportunity history, so the user can switch models without rebuilding their search
workflow.

OpportunityOS is local-first and deliberately small. An external agent owns conversation, web
search, browsing, interpretation, verification research, and delivery. OpportunityOS owns only the
durable state and deterministic checks needed to make that work survive a model change.

## What it stores

- **Profile** — flexible user context that helps an agent judge relevance.
- **Policy** — hard constraints such as freshness, location, official-source, and deadline rules.
- **Strategy** — human-readable search procedures that can be proposed, reviewed, revisioned, and
  rolled back.
- **History** — SQLite records of runs, candidates, deduplication, feedback, and source statistics.

The repository contains generic defaults and synthetic tests only. Private state lives in the
operating system’s application-data directory, or in `OPPORTUNITYOS_DATA_DIR` when configured.

## Install and initialize

```bash
uv sync
uv run opportunityos init
uv run opportunityos context --category jobs --format json
```

On Windows, the default state directory is under the user application-data location. It may be
overridden for tests or portable installations:

```powershell
$env:OPPORTUNITYOS_DATA_DIR = "$env:LOCALAPPDATA\OpportunityOS"
uv run opportunityos init
```

The runtime creates `profile.yaml`, `policy.yaml`, `strategy.yaml`, and `state.db` outside the Git
checkout. Users can inspect or update state through the CLI; manual YAML editing is optional.

## Agent protocol

An agent performs the search while OpportunityOS provides context and deterministic memory:

```text
intent -> context -> run start -> agent search and verification
       -> candidate check/record -> useful delivery -> run finish
       -> feedback -> optional strategy proposal
```

Example commands:

```bash
opportunityos run start --category jobs --agent hermes --model kimi --format json
opportunityos candidate check --json candidate.json --format json
opportunityos candidate record --run RUN_ID --json candidate.json --format json
opportunityos run finish RUN_ID --json summary.json --format json
opportunityos feedback add --json feedback.json --format json
```

Candidate input is versioned JSON. Unknown opportunity fields remain unknown rather than being
invented. Policy failures are reported with structured violations and do not mutate policy.

## CLI reference

```text
opportunityos init
opportunityos context --category CATEGORY --format json
opportunityos profile show|import|export|patch
opportunityos policy show|patch
opportunityos run start|finish
opportunityos candidate check|record
opportunityos feedback add
opportunityos strategy show|history|propose|rollback
opportunityos history recent|search
opportunityos export opportunityos-export.zip
opportunityos import opportunityos-export.zip
```

All agent-facing operations are non-interactive and support structured JSON output. Exit status is
zero for success, one for validation/user errors, two for local state errors, three for incompatible
state versions, and four for explicit policy enforcement failures.

## Hermes integration

Hermes is the reference integration, not a product requirement. Install the single generic skill
from [`skills/opportunityos/SKILL.md`](skills/opportunityos/SKILL.md) in the host agent’s skills
directory. It teaches the agent to recognize natural-language requests such as “find jobs,”
“search for scholarships,” “find research opportunities,” and “refresh my opportunities,” then use
the protocol above.

Hermes, Gemini CLI, Codex, or another host may provide browsing, scheduling, notifications, and
model access. OpportunityOS does not run a web server, scheduler, custom dashboard, Discord client,
MCP server, or autonomous search loop.

## Privacy and safety

Opportunity pages and imported files are untrusted data. Stored strategy text is data, not code, and
is never executed. ZIP imports reject traversal, unsupported members, incompatible versions, and
invalid databases. There is no telemetry by default and no capability to submit applications, send
messages, purchase anything, accept terms, or delete remote data.

Use [`PRIVACY.md`](PRIVACY.md) and [`SECURITY.md`](SECURITY.md) for the repository boundary and
security expectations. The v4 architecture is documented in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Development

```bash
uv sync --all-extras
uv run ruff check .
uv run mypy src
uv run pytest --cov=opportunityos --cov-fail-under=80
uv run python -m build
```

OpportunityOS is released under the [MIT License](LICENSE).
