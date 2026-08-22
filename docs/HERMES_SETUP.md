# Hermes setup

These steps are manual because they create an external runtime and OAuth credentials. Commands were
checked against Hermes' upstream documentation on 2026-08-21.

## 1. Install and verify on native Windows

The recommended path is the Hermes Desktop installer from the official site. For CLI-only native
Windows, review the remote script before running the upstream command:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

No administrator rights are required. Open a new PowerShell window, then run:

```powershell
Get-Command hermes
hermes --version
hermes doctor
```

## 2. Configure ChatGPT/Codex OAuth

Run `hermes model`, choose OpenAI Codex, and complete the displayed device-code login. Current Hermes
stores provider credentials in `%LOCALAPPDATA%\hermes\auth.json` on native Windows and can import an
existing Codex CLI store. A current explicit reauthentication command is:

```powershell
hermes auth add openai-codex
```

Never copy `auth.json` into this repository. OpportunityOS does not inspect it. Verify with a normal
Hermes chat before adding MCP or Discord. Plan quota behavior is owned by OpenAI/Hermes and is not
estimated by OpportunityOS.

## 3. Register the MCP server

Copy `examples/hermes-config.example.yaml` into your existing
`%LOCALAPPDATA%\hermes\config.yaml`, replacing `{REPOSITORY_PATH}` with the absolute clone path. Merge
the `mcp_servers` key; do not overwrite unrelated Hermes configuration. The example passes that
path through `OPPORTUNITYOS_REPOSITORY_ROOT`, so server behavior does not depend on Hermes' process
working directory. Then run:

```powershell
hermes mcp list
hermes mcp test opportunityos
```

The server uses stdio. Its allowlisted tools can read and write only OpportunityOS' private local
state and cannot submit, message, purchase, or accept terms.

## 4. Install the skills

Until this repository is published in a Hermes skill catalog, copy every directory under
`skills/` into `%LOCALAPPDATA%\hermes\skills\`, preserving directory names. This includes the
V2 behavioral skills `opportunityos-execution`, `opportunityos-brief`,
`opportunityos-followup`, and `opportunityos-health`, plus the V3.1
`opportunityos-profile-intelligence` skill. Check them with:

```powershell
hermes skills list
hermes skills check
```

Ask Hermes to run `opportunityos-profile-sync`, then `opportunityos-intake`, `-evaluate`, `-review`,
or `-prepare`. Add `opportunityos-scout` only after interactive flows pass; it now orchestrates
the V3 global discovery cycle while retaining V1/V2 category-scout compatibility. Run the V3.1
personal-intelligence skill interactively first and inspect its capability report before enabling its
05:00 schedule. An unavailable Gmail or continuous ChatGPT provider must remain visibly gated.

## 5. Gateway and automation

Configure messaging interactively with `hermes gateway setup`, then use `hermes gateway install` and
the `status`, `start`, `stop`, or `restart` subcommands. Native Windows uses a per-user Scheduled Task
or Startup fallback. Configure Discord before any cron job. The reviewed V3.1/V3 cron examples use a
personal-intelligence job at 05:00 followed by global jobs at 06:00 and 18:00 in the configured local
timezone; do not enable legacy staggered
category jobs at the same time unless deliberately testing compatibility. Cron examples are in
`examples/hermes-cron.md`; installing a skill does not silently schedule it.

Upstream references: [installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation/),
[native Windows](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native),
[providers](https://hermes-agent.nousresearch.com/docs/integrations/providers),
[MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp), and
[cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron).
