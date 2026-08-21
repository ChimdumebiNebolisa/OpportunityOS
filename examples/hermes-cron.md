# Reviewed Hermes cron examples

Create these only after interactive MCP, skills, Discord allowlist, and quiet-scout tests pass.
Schedules use the Hermes host timezone. Start with one daily category and inspect its first run.

```text
hermes cron create "0 8 * * *" "Run a bounded scholarship scout. Deliver only a material digest that passes the OpportunityOS gates; otherwise remain silent." --skill opportunityos-scout --name "OpportunityOS scholarships" --deliver discord
```

```text
hermes cron create "0 9 * * 1,4" "Run a bounded fellowship and research scout. Respect all MCP budgets and persist failures without retry loops." --skill opportunityos-scout --name "OpportunityOS fellowships" --deliver discord
```

Inspect, test, and pause with:

```text
hermes cron list
hermes cron run <job_id>
hermes cron pause <job_id>
```

OpportunityOS caps one run; Hermes owns scheduling and delivery. Never schedule `prepare`, READY,
lifecycle submission, or any external application action.
