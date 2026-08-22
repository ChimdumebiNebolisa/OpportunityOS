# Proposal: rebuild OpportunityOS around durable search memory

OpportunityOS v4 replaces the former application-management system with a portable protocol layer
for AI-assisted opportunity discovery. The product owns Profile, Policy, Strategy, and History;
external agents own conversation, web search, browsing, verification research, and delivery.

The rebuild is intentionally destructive. Application packets, execution queues, reminders,
follow-up, scoring, scouts, global discovery orchestration, custom Discord behavior, and required
MCP infrastructure are removed from the normal product surface.

## Outcomes

- A new installation initializes private YAML state and a SQLite history database.
- Agents can request compact context, record runs and candidates, add feedback, and propose safe
  strategy revisions through versioned JSON CLI commands.
- URL and fallback-fingerprint identity suppress duplicate results while allowing material changes.
- Policy remains deterministic and protected from strategy learning.
- The complete state can be exported and safely imported on another installation.
