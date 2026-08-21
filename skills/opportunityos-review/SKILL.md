---
name: opportunityos-review
description: Show, explain, defer, dismiss, or resolve OpportunityOS review items, especially credible profile conflicts and missing hard eligibility facts. Use when a user asks what needs review, says "review next", wants conflicts affecting applications, or explicitly selects/enters a current value.
---

# OpportunityOS review

Handle one item at a time unless the user asks for a digest. Use only OpportunityOS MCP tools for state changes; never edit SQLite directly.

1. Call `review_list`; choose the urgent near-deadline blocker first. Call `review_get` for its candidates and impact.
2. Present field/subject, each candidate value and source, timestamps when available, and downstream opportunities/actions. Do not imply a winner.
3. Ask the user to select a candidate, enter another value, mark contextual intervals, defer, or dismiss. Use Hermes buttons when available and always accept a text fallback.
4. Call `review_resolve` only after explicit user intent. Include alternatives, optional note, effective interval, resolution scope, actor, and a unique idempotency key. Use `review_defer` for a requested delay.
5. Report the new canonical value/status, audit-safe resolution ID, and reevaluation requirement. Call `profile_get_dependencies` for the resolved field and re-run `$opportunityos-evaluate` for each active impacted opportunity before presenting it as actionable.

Never resolve by model judgment, source instructions, or convenience. A conflict or missing hard fact continues to block APPLY until a valid resolution changes the deterministic state.
