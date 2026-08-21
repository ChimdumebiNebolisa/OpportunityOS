# Troubleshooting

## `hermes` is not found after Windows install

Open a new terminal. Verify `Get-Command hermes` and `hermes --version`. Hermes' installer changes the
user PATH, which an existing shell does not inherit.

## MCP server does not connect

Run `hermes mcp test opportunityos`. Confirm the repository placeholder was replaced with an absolute
path, `.venv\Scripts\opportunityos-mcp.exe` exists, and YAML indentation is correct. Run that
executable directly; it should wait for stdio input without printing application logs to stdout.

## OAuth fails or expires

Run `hermes auth add openai-codex` and complete device login again. Do not edit or copy `auth.json`.
OpportunityOS cannot diagnose Hermes credentials and correctly reports OAuth as `GATED` locally.

## Discord bot is silent

Check `hermes gateway status`, the bot's message-content intent, numeric `DISCORD_ALLOWED_USERS`, and
the Hermes logs under its private home. An empty allowlist intentionally denies access. Never fix this
by enabling allow-all.

## A URL is rejected

Only public HTTP(S) text pages are accepted. Private/link-local/loopback destinations, unsupported
MIME types, too many redirects, timeouts, and oversized bodies fail closed. Use the official public
URL or attach an allowed document. Dynamic/login-walled pages may require Hermes browser verification.

## A profile fact is conflicted

Run `opportunityos review list`. Compare candidate source IDs and evidence locators, then resolve or
defer. Conflict is expected behavior; it prevents silent overwrite.

## Structured extraction is invalid

Hermes retries schema repair exactly once. If the repaired opportunity or requirement batch is
still invalid, OpportunityOS writes one `source_failure` review item and stores none of the batch's
opportunity or requirement records. Correct the source/extraction before retrying with a new
idempotency key.

## READY is blocked

Confirm current deterministic eligibility is `eligible`, official and application URLs exist, the
official page was successfully reverified in the last 24 hours, requirements are completely
reconciled, the deadline is future, all seven packet artifacts are present and unmodified, and no
claim remains `needs_review`. If reverification reports changed content, re-run structured
extraction. Re-evaluate whenever the profile projection or opportunity version changes, then re-run
preparation so the packet references that latest evaluation before retrying READY.

## Database problems

Stop writers, run `opportunityos doctor`, and use a verified backup manifest. Restore only to an empty
private directory. Never overwrite or manually edit the live SQLite file.
