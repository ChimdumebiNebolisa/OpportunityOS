# Reviewed Hermes cron examples

Create these only after interactive MCP, skills, Discord allowlist, and quiet-discovery tests pass.
Schedules use the Hermes host timezone, which must match the configured OpportunityOS timezone.
The V3 default is two global cycles; keep the legacy category jobs paused while these are active.
The V3.1 personal-intelligence sweep runs before morning discovery. Create it only after the
personal-intelligence skill passes interactive MCP and capability checks.

```text
hermes cron create "0 5 * * *" "Run one bounded OpportunityOS V3.1 personal-intelligence sweep. Inspect source capabilities and sync state, read only enabled GitHub/Gmail/ChatGPT sources, record candidate observations with provenance and source timestamps, reconcile material changes through the deterministic profile service, and deliver only material review or capability changes; otherwise return [SILENT]. Never claim unsupported provider synchronization." --skill opportunityos-profile-intelligence --name "OpportunityOS personal intelligence" --deliver discord
```

```text
hermes cron create "0 6 * * *" "Run one bounded OpportunityOS V3 global discovery cycle. Load discovery state, cover all enabled lenses, persist bounded query/source outcomes, route candidates through the existing intake and deterministic gates, and deliver only material value; otherwise return [SILENT]." --skill opportunityos-scout --name "OpportunityOS global discovery morning" --deliver discord
```

```text
hermes cron create "0 18 * * *" "Run one bounded OpportunityOS V3 global discovery cycle. Recover one bounded catch-up window if needed, preserve exploration and profile-gap coverage, persist failures honestly, and deliver only material value; otherwise return [SILENT]." --skill opportunityos-scout --name "OpportunityOS global discovery evening" --deliver discord
```

Legacy V2 category schedule classes remain configurable under private `scouts.schedules` and include
scholarships, fellowships/research, grants/founder programs, competitions/selective technical
programs, and general high-upside opportunities. Keep those jobs paused when the V3 globals run.
Add behavioral jobs only after interactive MCP, Discord allowlist, and quiet-run checks pass:

```text
hermes cron create "0 18 * * *" "Run opportunityos-execution; deliver one material risk reminder or [SILENT]." --skill opportunityos-execution --name "OpportunityOS evening rescue" --deliver discord
hermes cron create "0 10 * * *" "Run opportunityos-brief daily; deliver the material brief or [SILENT]." --skill opportunityos-brief --name "OpportunityOS daily brief" --deliver discord
hermes cron create "0 11 * * 0" "Run opportunityos-brief weekly; deliver the advisory strategy brief or [SILENT]." --skill opportunityos-brief --name "OpportunityOS weekly strategy" --deliver discord
hermes cron create "0 12 * * *" "Run opportunityos-followup; prepare private due drafts and deliver only a material notice." --skill opportunityos-followup --name "OpportunityOS follow-up" --deliver discord
hermes cron create "30 12 * * *" "Run opportunityos-health; report actionable health or backup failures only." --skill opportunityos-health --name "OpportunityOS health" --deliver discord
```

Inspect, test, and pause with:

```text
hermes cron list
hermes cron run <job_id>
hermes cron pause <job_id>
```

OpportunityOS caps one run; Hermes owns scheduling and delivery. Never schedule `prepare`, READY,
lifecycle submission, or any external application action.
