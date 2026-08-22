"""Bounded personal-intelligence orchestration for V3.1."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from opportunityos.adapters.personal_sources import (
    AdapterCapability,
    ChatGPTPersonalAdapter,
    GitHubPersonalAdapter,
    GmailPersonalAdapter,
    PersonalSourceAdapter,
    PersonalSourceBatch,
    PersonalSourceUnavailableError,
    UnavailablePersonalAdapter,
)
from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.application.profile import ProfileService
from opportunityos.application.propagation import PropagationService
from opportunityos.domain.personal_intelligence import (
    candidate_fingerprint,
    classify_assertion,
    materiality,
    source_modes_valid,
)
from opportunityos.infrastructure.database import (
    AutomationControlRow,
    CanonicalFactRow,
    ObservationRow,
    PersonalSourceSyncStateRow,
    ProfileIntelligenceRunRow,
    ReconciliationBatchRow,
    ReviewItemRow,
    SourceRow,
)
from opportunityos.schemas import (
    ObservationInput,
    OfficialStatus,
    PersonalSourceBatchInput,
    PersonalSourceControlInput,
    PersonalSourceRecordInput,
    PersonalSourceType,
    ProfileIntelligenceFinishInput,
    SourceCreate,
    SourceType,
)
from opportunityos.util import new_id, utc_now

PERSONAL_SOURCE_TYPES = tuple(item.value for item in PersonalSourceType)
SOURCE_ROW_TYPES = {
    "github": SourceType.GITHUB_API.value,
    "gmail": SourceType.GMAIL_API.value,
    "chatgpt": SourceType.CHATGPT_CONTINUOUS.value,
}
CONTROL_KEY = "personal_intelligence"


class PersonalIntelligenceService:
    """Own run state while delegating canonical profile truth to ProfileService."""

    def __init__(
        self,
        context: ApplicationContext,
        adapters: Mapping[str, PersonalSourceAdapter] | None = None,
    ):
        self.context = context
        self.adapters = dict(adapters or self._default_adapters())

    def _default_adapters(self) -> dict[str, PersonalSourceAdapter]:
        username = os.environ.get("OPPORTUNITYOS_GITHUB_USERNAME", "").strip()
        github: PersonalSourceAdapter
        if username:
            github = GitHubPersonalAdapter(username)
        else:
            github = UnavailablePersonalAdapter("github", "github_username_not_configured")
        return {
            "github": github,
            "gmail": GmailPersonalAdapter(),
            "chatgpt": ChatGPTPersonalAdapter(),
        }

    @staticmethod
    def _source_setting(context: ApplicationContext, source_type: str) -> Any:
        return getattr(context.settings.profile_intelligence, source_type)

    @staticmethod
    def _source_row_type(source_type: str, mode: str | None = None) -> str:
        if source_type == "chatgpt" and mode == "snapshot_only":
            return SourceType.CHATGPT_SNAPSHOT.value
        return SOURCE_ROW_TYPES[source_type]

    def _control_enabled(self, session: Any) -> bool:
        row = session.get(AutomationControlRow, CONTROL_KEY)
        return bool(row.enabled) if row else self.context.settings.profile_intelligence.enabled

    def _ensure_source_states(self, session: Any) -> dict[str, PersonalSourceSyncStateRow]:
        states: dict[str, PersonalSourceSyncStateRow] = {}
        now = utc_now()
        for source_type in PERSONAL_SOURCE_TYPES:
            setting = self._source_setting(self.context, source_type)
            adapter = self.adapters.get(source_type)
            capability = (
                adapter.capability()
                if adapter
                else AdapterCapability(
                    source_type=source_type,
                    available=False,
                    operations=(),
                    authorization_status="unavailable",
                    detail_code="adapter_not_configured",
                )
            )
            row = session.get(PersonalSourceSyncStateRow, source_type)
            effective_mode = (
                row.configured_mode if row else (setting.mode if setting.enabled else "disabled")
            )
            if source_type == "chatgpt" and effective_mode == "snapshot_only":
                capability = AdapterCapability(
                    source_type="chatgpt",
                    available=True,
                    operations=("snapshot_import",),
                    authorization_status="local_snapshot",
                    detail_code="snapshot_only_available",
                )
            if row is None:
                mode = effective_mode
                row = PersonalSourceSyncStateRow(
                    source_type=source_type,
                    configured_mode=mode,
                    configured_scope=getattr(setting, "scope", {}),
                    actual_capabilities={
                        "available": capability.available,
                        "operations": list(capability.operations),
                    },
                    authorization_status=capability.authorization_status,
                    status="disabled"
                    if mode == "disabled"
                    else ("ready" if capability.available else "blocked"),
                    detail_code=capability.detail_code,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.configured_scope = getattr(setting, "scope", row.configured_scope)
                row.actual_capabilities = {
                    "available": capability.available,
                    "operations": list(capability.operations),
                }
                row.authorization_status = capability.authorization_status
                if row.configured_mode == "disabled":
                    row.status = "disabled"
                elif row.status == "disabled":
                    row.status = "ready" if capability.available else "blocked"
                row.detail_code = row.detail_code or capability.detail_code
                row.updated_at = now
            states[source_type] = row
        session.flush()
        return states

    def begin(self, *, idempotency_key: str | None = None) -> dict[str, Any]:
        operation = "profile_intelligence.begin"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            if not self._control_enabled(session):
                raise ValueError("Personal intelligence automation is disabled")
            active = session.scalar(
                select(ProfileIntelligenceRunRow).where(
                    ProfileIntelligenceRunRow.status == "running"
                )
            )
            if active:
                raise ValueError("A personal-intelligence run is already active")
            states = self._ensure_source_states(session)
            enabled_sources = [
                source_type
                for source_type, state in states.items()
                if state.configured_mode != "disabled"
            ]
            projection = int(
                session.scalar(select(func.max(CanonicalFactRow.projection_version))) or 0
            )
            run = ProfileIntelligenceRunRow(
                id=new_id(),
                profile_projection_version_before=projection,
                profile_projection_version_after=None,
                enabled_sources=enabled_sources,
                completed_sources=[],
                blocked_sources={},
                counters={
                    "records_inspected": 0,
                    "candidate_observations": 0,
                    "duplicate_observations": 0,
                    "suppressed_observations": 0,
                    "review_items_created": 0,
                    "canonical_changes": 0,
                    "model_calls": 0,
                },
                errors=[],
                status="running",
                delivery_result=None,
                started_at=utc_now(),
                ended_at=None,
            )
            session.add(run)
            audit(
                session,
                event_type="profile_intelligence_started",
                reason="bounded personal-intelligence sweep started",
                subject_type="profile_intelligence_run",
                subject_id=run.id,
                after_ids=[run.id],
                details={"enabled_sources": enabled_sources, "projection": projection},
            )
            result: dict[str, Any] = {
                "run_id": run.id,
                "status": run.status,
                "enabled_sources": enabled_sources,
                "profile_projection_version": projection,
                "source_states": [self._source_state_dict(row) for row in states.values()],
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def sync_source(self, run_id: str, source_type: PersonalSourceType) -> dict[str, Any]:
        source = source_type.value
        with self.context.database.transaction() as session:
            state = session.get(PersonalSourceSyncStateRow, source)
            if state is None:
                self._ensure_source_states(session)
                state = session.get(PersonalSourceSyncStateRow, source)
            if state is None:
                raise ValueError("Personal source state is unavailable")
            cursor = state.cursor
        adapter = self.adapters.get(source)
        if adapter is None:
            raise ValueError(f"No adapter configured for {source}")
        try:
            batch = adapter.fetch(
                cursor=cursor, limit=self._source_setting(self.context, source).max_records_per_run
            )
        except PersonalSourceUnavailableError as error:
            return self.record_source(
                run_id,
                PersonalSourceBatchInput(
                    source_type=source_type,
                    failed=True,
                    failure_detail=str(error),
                ),
            )
        return self.record_source(run_id, self._batch_input(source_type, batch))

    @staticmethod
    def _batch_input(
        source_type: PersonalSourceType, batch: PersonalSourceBatch
    ) -> PersonalSourceBatchInput:
        records = []
        for record in batch.records:
            records.append(
                PersonalSourceRecordInput(
                    locator=record.locator,
                    display_name=record.display_name,
                    content_fingerprint=record.content_fingerprint,
                    source_event_at=record.source_event_at,
                    observed_at=record.observed_at,
                    subject_identity=record.subject_identity,
                    evidence_excerpt=record.evidence_excerpt,
                    metadata=record.metadata or {},
                    observations=[
                        {
                            "field_path": item.field_path,
                            "value": item.value,
                            "evidence_locator": item.evidence_locator,
                            "extraction_confidence": item.extraction_confidence,
                            "assertion_kind": item.assertion_kind,
                            "source_event_at": item.source_event_at,
                            "effective_from": item.effective_from,
                            "effective_until": item.effective_until,
                            "observed_at": record.observed_at,
                            "subject_identity": item.subject_identity,
                            "extractor_model": item.extractor_model,
                        }
                        for item in record.observations
                    ],
                )
            )
        return PersonalSourceBatchInput(
            source_type=source_type,
            records=records,
            cursor_after=batch.cursor_after,
            high_water_mark=batch.high_water_mark,
            records_inspected=batch.records_inspected,
            model_calls=batch.model_calls,
        )

    def record_source(
        self,
        run_id: str,
        batch: PersonalSourceBatchInput,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "profile_intelligence.record_source"
        source = batch.source_type.value
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            run = session.get(ProfileIntelligenceRunRow, run_id)
            if run is None or run.status != "running":
                raise ValueError("Active personal-intelligence run not found")
            state = session.get(PersonalSourceSyncStateRow, source)
            if state is None:
                raise ValueError("Personal source state not initialized")
            if state.configured_mode == "disabled":
                raise ValueError(f"Personal source is disabled: {source}")
            now = utc_now()
            state.last_attempt_at = now
            if batch.failed:
                detail = batch.failure_detail or "source_failed"
                state.status = "blocked"
                state.detail_code = detail[:100]
                state.consecutive_failures += 1
                run.blocked_sources = {**run.blocked_sources, source: detail[:500]}
                run.errors = [*run.errors, f"{source}: {detail[:500]}"][-50:]
                result: dict[str, Any] = {
                    "run_id": run_id,
                    "source_type": source,
                    "status": "blocked",
                    "cursor": state.cursor,
                }
                store_idempotent(session, idempotency_key, operation, result)
                return result
            prior_cursor = state.cursor
            configured_mode = state.configured_mode

        profile = ProfileService(self.context)
        observation_inputs: list[ObservationInput] = []
        project_inputs: list[ObservationInput] = []
        deferred_inputs: list[ObservationInput] = []
        source_ids: list[str] = []
        duplicate_records = 0
        suppressed = 0
        changed_fields: set[str] = set()
        seen_fingerprints: set[str] = set()
        try:
            for record in batch.records:
                if record.content_fingerprint in seen_fingerprints:
                    duplicate_records += 1
                    continue
                seen_fingerprints.add(record.content_fingerprint)
                with self.context.database.transaction() as session:
                    existing_source = session.scalar(
                        select(SourceRow).where(
                            SourceRow.source_type == self._source_row_type(source, configured_mode),
                            SourceRow.content_hash == record.content_fingerprint,
                        )
                    )
                if existing_source is not None:
                    duplicate_records += 1
                    continue
                source_id = profile.add_source(
                    SourceCreate(
                        source_type=SourceType(self._source_row_type(source, configured_mode)),
                        source_locator=record.locator,
                        display_name=record.display_name,
                        official_status=(
                            OfficialStatus.OFFICIAL
                            if source == "github"
                            else OfficialStatus.UNKNOWN
                        ),
                        retrieved_at=now,
                        published_at=record.source_event_at,
                        content_hash=record.content_fingerprint,
                        mime_type="application/json",
                        trust_class=("objective_provider" if source == "github" else "candidate"),
                        metadata={
                            **record.metadata,
                            "personal_source_type": source,
                            "evidence_excerpt": record.evidence_excerpt[:5000],
                            "subject_identity": record.subject_identity,
                        },
                    )
                )
                source_ids.append(source_id)
                for proposal in record.observations:
                    classification = classify_assertion(
                        text=record.evidence_excerpt,
                        subject_identity=proposal.subject_identity or record.subject_identity,
                        assertion_kind=proposal.assertion_kind,
                    )
                    if not classification.eligible_for_profile:
                        suppressed += 1
                        continue
                    fp = proposal.content_fingerprint or candidate_fingerprint(
                        field_path=proposal.field_path,
                        value=proposal.value,
                        effective_from=proposal.effective_from,
                        source_event_at=proposal.source_event_at or record.source_event_at,
                        content_fingerprint_value=record.content_fingerprint,
                    )
                    with self.context.database.transaction() as session:
                        duplicate = session.scalar(
                            select(ObservationRow.id).where(
                                ObservationRow.content_fingerprint == fp
                            )
                        )
                        current = session.scalar(
                            select(CanonicalFactRow).where(
                                CanonicalFactRow.field_path == proposal.field_path
                            )
                        )
                    if duplicate:
                        duplicate_records += 1
                        continue
                    decision = materiality(
                        field_path=proposal.field_path,
                        value=proposal.value,
                        current_value=current.typed_value if current else None,
                        confidence=proposal.extraction_confidence,
                        assertion_kind=classification.assertion_kind,
                        threshold=self.context.settings.profile_intelligence.reconciliation.materiality_threshold,
                    )
                    if decision.material:
                        changed_fields.add(proposal.field_path)
                    observation = ObservationInput(
                        field_path=proposal.field_path,
                        value=proposal.value,
                        value_type=proposal.value_type,
                        assertion_kind=classification.assertion_kind,
                        source_id=source_id,
                        evidence_locator=proposal.evidence_locator or record.locator,
                        extraction_confidence=proposal.extraction_confidence,
                        effective_from=proposal.effective_from,
                        effective_until=proposal.effective_until,
                        observed_at=proposal.observed_at,
                        source_event_at=proposal.source_event_at or record.source_event_at,
                        subject_identity=classification.subject_identity,
                        content_fingerprint=fp,
                        extractor_model=proposal.extractor_model,
                        extraction_schema_version=proposal.extraction_schema_version,
                    )
                    observation_inputs.append(observation)
                    if not decision.material and decision.reason == "below_threshold":
                        deferred_inputs.append(observation)
                    else:
                        project_inputs.append(observation)
            projected_result = (
                profile.submit_observations(
                    project_inputs,
                    idempotency_key=f"{idempotency_key}:observations" if idempotency_key else None,
                    actor=f"personal_intelligence:{source}",
                )
                if project_inputs
                else {"observation_ids": [], "reconciliation": []}
            )
            deferred_result = (
                profile.submit_observations(
                    deferred_inputs,
                    idempotency_key=f"{idempotency_key}:deferred" if idempotency_key else None,
                    actor=f"personal_intelligence:{source}:deferred",
                    reconcile=False,
                )
                if deferred_inputs
                else {"observation_ids": [], "reconciliation": []}
            )
            profile_result = {
                "observation_ids": [
                    *projected_result["observation_ids"],
                    *deferred_result["observation_ids"],
                ],
                "reconciliation": projected_result["reconciliation"],
            }
        except Exception as error:
            detail = str(error)[:500] or "source_processing_failed"
            with self.context.database.transaction() as session:
                run = session.get(ProfileIntelligenceRunRow, run_id)
                state = session.get(PersonalSourceSyncStateRow, source)
                if run and state:
                    state.status = "blocked"
                    state.detail_code = "processing_failed"
                    state.consecutive_failures += 1
                    run.blocked_sources = {**run.blocked_sources, source: detail}
                    run.errors = [*run.errors, f"{source}: {detail}"][-50:]
            raise

        material_reviews = sum(
            1 for item in profile_result["reconciliation"] if item.get("status") == "conflicted"
        )
        inspected = max(batch.records_inspected, len(batch.records))
        with self.context.database.transaction() as session:
            run = session.get(ProfileIntelligenceRunRow, run_id)
            state = session.get(PersonalSourceSyncStateRow, source)
            if run is None or state is None or run.status != "running":
                raise ValueError("Personal-intelligence run was closed during source processing")
            counters = dict(run.counters)
            counters["records_inspected"] = counters.get("records_inspected", 0) + inspected
            counters["candidate_observations"] = counters.get("candidate_observations", 0) + len(
                observation_inputs
            )
            counters["duplicate_observations"] = (
                counters.get("duplicate_observations", 0) + duplicate_records
            )
            counters["suppressed_observations"] = (
                counters.get("suppressed_observations", 0) + suppressed
            )
            counters["review_items_created"] = (
                counters.get("review_items_created", 0) + material_reviews
            )
            counters["model_calls"] = counters.get("model_calls", 0) + batch.model_calls
            counters["changed_fields"] = len(changed_fields)
            run.counters = counters
            state.records_inspected += inspected
            state.candidate_observations += len(observation_inputs)
            state.review_items_created += material_reviews
            state.last_record_timestamp = batch.high_water_mark or state.last_record_timestamp
            state.cursor = batch.cursor_after or state.cursor
            state.high_water_mark = batch.high_water_mark or state.high_water_mark
            state.last_success_at = now
            state.consecutive_failures = 0
            state.status = "ready"
            state.detail_code = "sync_complete"
            if source not in run.completed_sources:
                run.completed_sources = [*run.completed_sources, source]
            audit(
                session,
                event_type="profile_intelligence_source_completed",
                reason="personal source batch processed through profile ledger",
                subject_type="personal_source",
                subject_id=source,
                actor="personal_intelligence",
                after_ids=source_ids + profile_result["observation_ids"],
                details={
                    "run_id": run_id,
                    "records": len(batch.records),
                    "observations": len(observation_inputs),
                    "duplicates": duplicate_records,
                    "suppressed": suppressed,
                    "changed_fields": sorted(changed_fields),
                    "cursor_before": prior_cursor,
                    "cursor_after": state.cursor,
                },
            )
            result = {
                "run_id": run_id,
                "source_type": source,
                "status": "complete",
                "records_inspected": inspected,
                "candidate_observations": len(observation_inputs),
                "duplicate_observations": duplicate_records,
                "suppressed_observations": suppressed,
                "reconciliation": profile_result["reconciliation"],
                "cursor": state.cursor,
                "high_water_mark": (
                    state.high_water_mark.isoformat() if state.high_water_mark else None
                ),
            }
            store_idempotent(session, idempotency_key, operation, result)
        if changed_fields:
            result["propagation"] = PropagationService(self.context).reevaluate_dependents(
                sorted(changed_fields), limit=20
            )
        return result

    def finish(
        self,
        run_id: str,
        value: ProfileIntelligenceFinishInput | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "profile_intelligence.finish"
        finish_value = value or ProfileIntelligenceFinishInput()
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            run = session.get(ProfileIntelligenceRunRow, run_id)
            if run is None or run.status != "running":
                raise ValueError("Active personal-intelligence run not found")
            open_reviews = session.scalars(
                select(ReviewItemRow).where(
                    ReviewItemRow.status == "open",
                    ReviewItemRow.created_at >= run.started_at,
                )
            ).all()
            material_ids = [row.id for row in open_reviews][
                : self.context.settings.profile_intelligence.review_digest_max_items
            ]
            fingerprint = hashlib.sha256(
                json.dumps(material_ids, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            batch = session.scalar(
                select(ReconciliationBatchRow).where(
                    ReconciliationBatchRow.delivery_fingerprint == fingerprint
                )
            )
            if batch is None:
                batch = ReconciliationBatchRow(
                    id=new_id(),
                    profile_intelligence_run_id=run.id,
                    material_item_ids=material_ids,
                    delivery_fingerprint=fingerprint,
                    delivered_at=None,
                    status="material" if material_ids else "silent",
                    created_at=utc_now(),
                )
                session.add(batch)
            projection_after = int(
                session.scalar(select(func.max(CanonicalFactRow.projection_version))) or 0
            )
            all_completed = set(run.completed_sources) >= set(run.enabled_sources)
            run.profile_projection_version_after = projection_after
            run.ended_at = utc_now()
            run.errors = [*run.errors, *finish_value.errors][-50:]
            run.status = "completed" if all_completed and not run.blocked_sources else "partial"
            run.delivery_result = "material" if material_ids else finish_value.delivery_result
            audit(
                session,
                event_type="profile_intelligence_finished",
                reason="personal-intelligence sweep completed with honest source coverage",
                subject_type="profile_intelligence_run",
                subject_id=run.id,
                after_ids=[batch.id],
                details={
                    "status": run.status,
                    "completed_sources": run.completed_sources,
                    "blocked_sources": run.blocked_sources,
                    "review_batch_id": batch.id,
                },
            )
            result = {
                "run_id": run.id,
                "status": run.status,
                "delivery_result": run.delivery_result,
                "profile_projection_version_before": run.profile_projection_version_before,
                "profile_projection_version_after": projection_after,
                "completed_sources": run.completed_sources,
                "blocked_sources": run.blocked_sources,
                "counters": run.counters,
                "errors": run.errors,
                "reconciliation_batch": self._batch_dict(batch),
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def run_once(self, *, idempotency_key: str | None = None) -> dict[str, Any]:
        begun = self.begin(idempotency_key=f"{idempotency_key}:begin" if idempotency_key else None)
        run_id = str(begun["run_id"])
        for source_type in PersonalSourceType:
            if source_type.value in begun["enabled_sources"]:
                self.sync_source(run_id, source_type)
        return self.finish(
            run_id, idempotency_key=f"{idempotency_key}:finish" if idempotency_key else None
        )

    def capabilities(self) -> list[dict[str, Any]]:
        with self.context.database.transaction() as session:
            states = self._ensure_source_states(session)
            return [self._source_state_dict(row) for row in states.values()]

    def sync_states(self) -> list[dict[str, Any]]:
        with self.context.database.transaction() as session:
            states = self._ensure_source_states(session)
            return [self._source_state_dict(row) for row in states.values()]

    def set_source_control(self, value: PersonalSourceControlInput) -> dict[str, Any]:
        source = value.source_type.value
        if value.mode and not source_modes_valid(source, value.mode):
            raise ValueError(f"Unsupported mode for {source}: {value.mode}")
        mode = value.mode or ("continuous" if value.enabled else "disabled")
        if not value.enabled:
            mode = "disabled"
        with self.context.database.transaction() as session:
            self._ensure_source_states(session)
            state = session.get(PersonalSourceSyncStateRow, source)
            if state is None:
                raise ValueError("Personal source state not found")
            state.configured_mode = mode
            state.status = "disabled" if mode == "disabled" else state.status
            state.detail_code = value.reason[:100]
            state.updated_at = utc_now()
            audit(
                session,
                event_type="personal_source_control_changed",
                reason=value.reason[:500],
                subject_type="personal_source",
                subject_id=source,
                actor="user",
                details={"mode": mode, "enabled": mode != "disabled"},
            )
            return self._source_state_dict(state)

    def review_batches(self, *, limit: int = 10) -> list[dict[str, Any]]:
        if limit < 1 or limit > 100:
            raise ValueError("Review batch limit must be between 1 and 100")
        with self.context.database.transaction() as session:
            rows = session.scalars(
                select(ReconciliationBatchRow)
                .order_by(ReconciliationBatchRow.created_at.desc())
                .limit(limit)
            ).all()
            return [self._batch_dict(row) for row in rows]

    def status(self) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            states = self._ensure_source_states(session)
            latest = session.scalar(
                select(ProfileIntelligenceRunRow).order_by(
                    ProfileIntelligenceRunRow.started_at.desc()
                )
            )
            return {
                "enabled": self.context.settings.profile_intelligence.enabled,
                "schedule": self.context.settings.profile_intelligence.schedule,
                "timezone": self.context.settings.profile_intelligence.timezone,
                "latest_run": self._run_dict(latest) if latest else None,
                "sources": [self._source_state_dict(row) for row in states.values()],
            }

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _source_state_dict(row: PersonalSourceSyncStateRow) -> dict[str, Any]:
        return {
            "source_type": row.source_type,
            "configured_mode": row.configured_mode,
            "configured_scope": row.configured_scope,
            "actual_capabilities": row.actual_capabilities,
            "authorization_status": row.authorization_status,
            "cursor": row.cursor,
            "high_water_mark": PersonalIntelligenceService._iso(row.high_water_mark),
            "last_attempt_at": PersonalIntelligenceService._iso(row.last_attempt_at),
            "last_success_at": PersonalIntelligenceService._iso(row.last_success_at),
            "last_record_timestamp": PersonalIntelligenceService._iso(row.last_record_timestamp),
            "records_inspected": row.records_inspected,
            "candidate_observations": row.candidate_observations,
            "review_items_created": row.review_items_created,
            "canonical_changes": row.canonical_changes,
            "consecutive_failures": row.consecutive_failures,
            "status": row.status,
            "detail_code": row.detail_code,
        }

    @staticmethod
    def _run_dict(row: ProfileIntelligenceRunRow) -> dict[str, Any]:
        return {
            "run_id": row.id,
            "status": row.status,
            "profile_projection_version_before": row.profile_projection_version_before,
            "profile_projection_version_after": row.profile_projection_version_after,
            "enabled_sources": row.enabled_sources,
            "completed_sources": row.completed_sources,
            "blocked_sources": row.blocked_sources,
            "counters": row.counters,
            "errors": row.errors,
            "delivery_result": row.delivery_result,
            "started_at": PersonalIntelligenceService._iso(row.started_at),
            "ended_at": PersonalIntelligenceService._iso(row.ended_at),
        }

    @staticmethod
    def _batch_dict(row: ReconciliationBatchRow) -> dict[str, Any]:
        return {
            "batch_id": row.id,
            "run_id": row.profile_intelligence_run_id,
            "material_item_ids": row.material_item_ids,
            "delivery_fingerprint": row.delivery_fingerprint,
            "delivered_at": PersonalIntelligenceService._iso(row.delivered_at),
            "status": row.status,
            "created_at": PersonalIntelligenceService._iso(row.created_at),
        }
