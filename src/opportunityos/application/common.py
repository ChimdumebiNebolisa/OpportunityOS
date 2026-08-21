"""Shared transaction helpers without domain behavior."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from opportunityos.infrastructure.database import AuditEventRow, IdempotencyRow
from opportunityos.util import new_id, utc_now


def idempotent_result(session: Session, key: str | None, operation: str) -> dict[str, Any] | None:
    if not key:
        return None
    row = session.get(IdempotencyRow, key)
    if row is None:
        return None
    if row.operation != operation:
        raise ValueError("Idempotency key was already used for a different operation")
    return row.result_json


def store_idempotent(
    session: Session, key: str | None, operation: str, result: dict[str, Any]
) -> None:
    if key:
        session.add(
            IdempotencyRow(key=key, operation=operation, result_json=result, created_at=utc_now())
        )


def audit(
    session: Session,
    *,
    event_type: str,
    reason: str,
    subject_type: str,
    subject_id: str | None,
    actor: str = "system",
    before_ids: list[str] | None = None,
    after_ids: list[str] | None = None,
    ruleset_version: str | None = None,
    details: dict[str, Any] | None = None,
) -> str:
    event_id = new_id()
    session.add(
        AuditEventRow(
            id=event_id,
            event_type=event_type,
            actor=actor,
            reason=reason,
            subject_type=subject_type,
            subject_id=subject_id,
            before_ids=before_ids or [],
            after_ids=after_ids or [],
            ruleset_version=ruleset_version,
            details=details or {},
            created_at=utc_now(),
        )
    )
    return event_id
