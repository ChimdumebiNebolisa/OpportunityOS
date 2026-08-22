## Purpose

Ranks the user's highest-leverage unfinished opportunity work and reminds them only when a deterministic value, urgency, or completion-risk threshold justifies interruption.

## ADDED Requirements

### Requirement: Execution priority accounts for completion leverage
The action queue MUST deterministically account for opportunity value, urgency, readiness, remaining human effort, completion ratio, completion leverage, deadline risk, dependency readiness, available time, packet readiness, and whether the action unlocks submission. The priority rules MUST be versioned and return one primary action first.

#### Scenario: Nearly complete urgent work outranks distant work
- **WHEN** a high-value action is nearly complete and fits the user's time budget while a marginally higher-scoring action is distant and effort-heavy
- **THEN** the nearly complete action is returned as the primary recommendation

#### Scenario: No action fits
- **WHEN** no current actionable item fits the available time or current-state requirements
- **THEN** the system returns an explicit empty recommendation without creating a stale or speculative action

### Requirement: Reminders require material unfinished risk
A reminder MUST require an APPLY opportunity, a READY or IN_PROGRESS action, value above the configured threshold, approaching deadline or high completion leverage, no completion or active snooze/stop, a new or escalated fingerprint, and remaining notification budget.

#### Scenario: Deadline rescue reminder
- **WHEN** a qualifying action is urgent and has not been completed, snoozed, or stopped
- **THEN** the system creates a tiered reminder containing only the minimum useful title, deadline, remaining work, packet state, and next action

#### Scenario: Low-value or completed action
- **WHEN** an action is low value, complete, blocked by stale evaluation, or not an APPLY opportunity
- **THEN** no proactive reminder is delivered

### Requirement: Users control reminder state deterministically
The system MUST support local snooze, stop, pass, applied/submitted, and no-longer-doing-this transitions with explicit timestamps, reasons, and idempotent behavior.

#### Scenario: Snooze
- **WHEN** the user snoozes an action until a specified or configured time
- **THEN** reminders for that action are suppressed until that time and the state is persisted

#### Scenario: Stop reminders
- **WHEN** the user stops reminders for an opportunity
- **THEN** future equivalent reminders are suppressed until an explicit local state change reopens them

### Requirement: Notification noise is capped and suppressed
Proactive notifications MUST respect daily caps and quiet hours, prioritize deadline rescue and blocking review above lower-priority classes, and suppress duplicate fingerprints unless urgency or material state changes.

#### Scenario: Cap reached
- **WHEN** more qualifying notifications exist than the configured daily cap
- **THEN** only the highest-priority items within the cap are delivered and the remaining items remain persisted for later evaluation
