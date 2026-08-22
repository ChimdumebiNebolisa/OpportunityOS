from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from opportunityos.adapters.personal_sources import (
    AdapterCapability,
    PersonalCandidate,
    PersonalSourceBatch,
    PersonalSourceRecord,
)
from opportunityos.application.personal_intelligence import PersonalIntelligenceService
from opportunityos.config.settings import ProfileIntelligenceSettings
from opportunityos.domain.personal_intelligence import (
    candidate_fingerprint,
    classify_assertion,
    content_fingerprint,
    materiality,
)
from opportunityos.schemas import (
    PersonalSourceBatchInput,
    PersonalSourceControlInput,
    PersonalSourceRecordInput,
    PersonalSourceType,
    ProfileIntelligenceFinishInput,
)


class FakeAdapter:
    def __init__(self, source_type: str, batch: PersonalSourceBatch) -> None:
        self.source_type = source_type
        self.batch = batch
        self.calls = 0

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            source_type=self.source_type,
            available=True,
            operations=("read",),
            authorization_status="authorized",
            detail_code="fake_available",
        )

    def fetch(self, *, cursor: str | None, limit: int) -> PersonalSourceBatch:
        self.calls += 1
        if cursor == self.batch.cursor_after:
            return PersonalSourceBatch((), cursor, self.batch.high_water_mark, 0)
        return self.batch


def _batch(source_type: str, field_path: str, value: Any, fingerprint: str) -> PersonalSourceBatch:
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    return PersonalSourceBatch(
        records=(
            PersonalSourceRecord(
                locator=f"{source_type}:synthetic-record",
                display_name=f"Synthetic {source_type}",
                content_fingerprint=fingerprint,
                observed_at=now,
                source_event_at=now,
                evidence_excerpt="A direct user-authored synthetic profile fact.",
                observations=(
                    PersonalCandidate(
                        field_path=field_path,
                        value=value,
                        evidence_locator=f"{source_type}:synthetic-record",
                        extraction_confidence=0.95,
                        assertion_kind="direct_assertion",
                        source_event_at=now,
                    ),
                ),
            ),
        ),
        cursor_after=fingerprint,
        high_water_mark=now,
        records_inspected=1,
    )


def _service(
    context: Any, *, batches: dict[str, PersonalSourceBatch] | None = None
) -> PersonalIntelligenceService:
    values = batches or {}
    adapters = {
        source: FakeAdapter(
            source,
            values.get(
                source,
                PersonalSourceBatch((), None, None, 0),
            ),
        )
        for source in ("github", "gmail", "chatgpt")
    }
    return PersonalIntelligenceService(context, adapters=adapters)


def test_personal_policy_classifies_untrusted_assertions() -> None:
    assert classify_assertion(
        text="If I get this, I might move", subject_identity="user"
    ).eligible_for_profile
    assert (
        classify_assertion(
            text="This is about my friend", subject_identity="third_party"
        ).assertion_kind
        == "third_party"
    )
    assert not classify_assertion(text="A summary", author_role="assistant").eligible_for_profile
    assert (
        classify_assertion(text="No, my graduation is 2027", subject_identity="user").assertion_kind
        == "correction"
    )
    record_fp = content_fingerprint(locator="gmail:1", content="acceptance")
    assert len(record_fp) == 64
    assert (
        len(
            candidate_fingerprint(
                field_path="education.gpa",
                value=3.8,
                effective_from=None,
                source_event_at=None,
                content_fingerprint_value=record_fp,
            )
        )
        == 64
    )
    assert not materiality(
        field_path="education.gpa",
        value=3.8,
        current_value=3.8,
        confidence=1,
        assertion_kind="direct_assertion",
        threshold=0.65,
    ).material


def test_daily_run_tracks_sources_projection_and_cursors(context_factory: Any) -> None:
    context = context_factory()
    service = _service(
        context,
        batches={
            "github": _batch("github", "github.repositories.demo.exists", True, "a" * 64),
            "gmail": _batch("gmail", "career.current_status", "research", "b" * 64),
        },
    )
    result = service.run_once(idempotency_key="personal-run")
    assert result["status"] == "completed"
    assert set(result["completed_sources"]) == {"github", "gmail", "chatgpt"}
    status = service.status()
    assert status["latest_run"]["profile_projection_version_after"] >= 1
    states = {item["source_type"]: item for item in status["sources"]}
    assert states["github"]["cursor"] == "a" * 64
    assert states["gmail"]["cursor"] == "b" * 64


def test_duplicate_personal_record_is_silent(context_factory: Any) -> None:
    context = context_factory()
    service = _service(context)
    begun = service.begin()
    source_batch = PersonalSourceBatchInput(
        source_type=PersonalSourceType.GITHUB,
        records=[
            PersonalSourceRecordInput(
                locator="github:demo",
                display_name="Synthetic GitHub",
                content_fingerprint="c" * 64,
                observed_at=datetime.now(UTC),
                evidence_excerpt="Objective metadata",
                observations=[
                    {
                        "field_path": "github.repositories.demo.exists",
                        "value": True,
                        "observed_at": datetime.now(UTC),
                        "extraction_confidence": 1,
                        "assertion_kind": "observed",
                    }
                ],
            )
        ],
        cursor_after="c" * 64,
        records_inspected=1,
    )
    first = service.record_source(begun["run_id"], source_batch)
    second = service.record_source(begun["run_id"], source_batch)
    assert first["candidate_observations"] == 1
    assert second["candidate_observations"] == 0
    assert second["duplicate_observations"] >= 1
    assert service.finish(begun["run_id"])["delivery_result"] == "silent"


def test_source_failure_preserves_cursor_and_other_sources_continue(context_factory: Any) -> None:
    context = context_factory()
    service = _service(context)
    begun = service.begin()
    failed = service.record_source(
        begun["run_id"],
        PersonalSourceBatchInput(
            source_type=PersonalSourceType.GMAIL,
            failed=True,
            failure_detail="gmail_auth_required",
        ),
    )
    assert failed["status"] == "blocked"
    state = {item["source_type"]: item for item in service.sync_states()}["gmail"]
    assert state["cursor"] is None
    assert state["consecutive_failures"] == 1
    finished = service.finish(
        begun["run_id"],
        ProfileIntelligenceFinishInput(delivery_result="partial"),
    )
    assert finished["status"] == "partial"


def test_source_control_disables_one_source_without_deleting_history(context_factory: Any) -> None:
    context = context_factory()
    service = _service(context)
    service.set_source_control(
        PersonalSourceControlInput(
            source_type=PersonalSourceType.GMAIL,
            enabled=False,
            reason="synthetic pause",
        )
    )
    begun = service.begin()
    assert "gmail" not in begun["enabled_sources"]
    assert any(item["source_type"] == "gmail" for item in service.sync_states())


def test_snapshot_classification_suppresses_hypothetical_and_third_party(
    context_factory: Any,
) -> None:
    context = context_factory()
    service = _service(context)
    service.set_source_control(
        PersonalSourceControlInput(
            source_type=PersonalSourceType.CHATGPT,
            enabled=True,
            mode="snapshot_only",
        )
    )
    begun = service.begin()
    batch = PersonalSourceBatchInput(
        source_type=PersonalSourceType.CHATGPT,
        records=[
            PersonalSourceRecordInput(
                locator="chatgpt:snapshot:1",
                display_name="Synthetic ChatGPT snapshot",
                content_fingerprint="d" * 64,
                observed_at=datetime.now(UTC),
                evidence_excerpt="Hypothetically, my friend may apply.",
                observations=[
                    {
                        "field_path": "goals.target_program",
                        "value": "other-person-program",
                        "observed_at": datetime.now(UTC),
                        "extraction_confidence": 0.9,
                        "assertion_kind": "hypothetical",
                        "subject_identity": "third_party",
                    }
                ],
            )
        ],
        cursor_after="d" * 64,
        records_inspected=1,
    )
    result = service.record_source(begun["run_id"], batch)
    assert result["candidate_observations"] == 0
    assert result["suppressed_observations"] == 1


def test_invalid_personal_source_batch_is_rejected() -> None:
    with pytest.raises(ValueError):
        PersonalSourceRecordInput(
            locator="gmail:1",
            display_name="Bad",
            content_fingerprint="not-a-fingerprint",
            observed_at=datetime.now(UTC),
        )


def test_personal_intelligence_settings_reject_unsafe_values() -> None:
    with pytest.raises(ValueError):
        ProfileIntelligenceSettings(schedule="25:00")
    with pytest.raises(ValueError):
        ProfileIntelligenceSettings(max_duration_seconds=30)
    with pytest.raises(ValueError):
        PersonalSourceControlInput(
            source_type=PersonalSourceType.GMAIL, enabled=True, mode="invalid"
        )
