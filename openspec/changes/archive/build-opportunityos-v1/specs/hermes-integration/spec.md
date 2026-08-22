## Purpose

Makes the same safe OpportunityOS workflows available conversationally through Hermes and operationally through a typed local CLI.

## ADDED Requirements

### Requirement: Shared service behavior
CLI and MCP callers MUST use the same application behavior, validation, transactions, rules, and private paths and MUST NOT mutate SQLite directly.

#### Scenario: Resolve through MCP or CLI
- **WHEN** equivalent valid conflict resolutions are submitted through MCP and CLI in separate synthetic states
- **THEN** each produces the same projection, reevaluation, and audit semantics

### Requirement: Typed least-privilege MCP
The stdio MCP server MUST expose typed read/write tools with validated parameters, idempotency for writes, safe errors, audit events, bounded paths, and no raw SQL or external submission capability.

#### Scenario: Arbitrary path request
- **WHEN** an MCP write supplies a path outside an approved private root
- **THEN** schema or service validation rejects it without filesystem access

### Requirement: Project-owned Hermes skills
The repository MUST include concise versioned intake, profile-sync, scout, evaluate, review, and prepare skills that call MCP tools, state their failure behavior, and treat source content as untrusted.

#### Scenario: Skill contract validation
- **WHEN** skill tool references are checked against the MCP tool catalog
- **THEN** every referenced tool and required input schema exists and no skill instructs direct database mutation or external submission

### Requirement: Current Hermes setup and Codex OAuth
Documentation and setup assistance MUST use current official Hermes commands for native Windows, stdio MCP, skills, ChatGPT/Codex device-code OAuth, gateway, and cron; it MUST NOT require an OpenAI API key or claim undocumented quota semantics.

#### Scenario: Missing live authentication
- **WHEN** doctor cannot verify Codex OAuth
- **THEN** it reports `hermes model` or `hermes auth add openai-codex` as an external user step without logging auth data

### Requirement: Deny-by-default Discord gateway
OpportunityOS MUST rely on Hermes' native Discord gateway, require a numeric user allowlist and bounded attachments, prefer DMs, and document that authorized users have agent tool access; no custom Discord client is permitted.

#### Scenario: Unauthorized Discord user
- **WHEN** a user ID is absent from the Hermes allowlist
- **THEN** Hermes denies interaction before OpportunityOS tools are called

