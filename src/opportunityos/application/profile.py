"""Profile evidence, projection, review, and human-resolution interface."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunityos.adapters.github import GitHubAuthRequiredError, GitHubClient
from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.domain.profile import Candidate, reconcile_field
from opportunityos.infrastructure.database import (
    CanonicalFactRow,
    HumanResolutionRow,
    ObservationRow,
    ReviewItemRow,
    SourceRow,
)
from opportunityos.schemas import (
    ObservationInput,
    ObservationStatus,
    OfficialStatus,
    ResolutionInput,
    ReviewStatus,
    ReviewType,
    SourceCreate,
    SourceType,
)
from opportunityos.util import new_id, utc_now


class ProfileService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def add_source(self, value: SourceCreate, idempotency_key: str | None = None) -> str:
        operation = "profile.add_source"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return str(previous["source_id"])
            source_id = new_id()
            session.add(
                SourceRow(
                    id=source_id,
                    **value.model_dump(exclude={"metadata"}),
                    metadata_json=value.metadata,
                    created_at=utc_now(),
                )
            )
            audit(
                session,
                event_type="source_added",
                reason="validated profile source",
                subject_type="source",
                subject_id=source_id,
                after_ids=[source_id],
            )
            store_idempotent(session, idempotency_key, operation, {"source_id": source_id})
            return source_id

    def submit_observations(
        self,
        values: list[ObservationInput],
        *,
        idempotency_key: str | None = None,
        actor: str = "hermes",
    ) -> dict[str, Any]:
        if not values:
            raise ValueError("At least one observation is required")
        operation = "profile.submit_observations"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            source_ids = {value.source_id for value in values}
            existing_sources = set(
                session.scalars(select(SourceRow.id).where(SourceRow.id.in_(source_ids))).all()
            )
            missing = sorted(source_ids - existing_sources)
            if missing:
                raise ValueError(f"Unknown source identifiers: {missing}")
            observation_ids: list[str] = []
            fields: set[str] = set()
            for value in values:
                observation_id = new_id()
                fields.add(value.field_path)
                observation_ids.append(observation_id)
                session.add(
                    ObservationRow(
                        id=observation_id,
                        subject_type="profile",
                        subject_id=None,
                        field_path=value.field_path,
                        typed_value=value.value,
                        value_type=value.value_type,
                        assertion_kind=value.assertion_kind,
                        source_id=value.source_id,
                        evidence_locator=value.evidence_locator,
                        extraction_confidence=value.extraction_confidence,
                        effective_from=value.effective_from,
                        effective_until=value.effective_until,
                        observed_at=value.observed_at,
                        extractor_model=value.extractor_model,
                        extraction_schema_version=value.extraction_schema_version,
                        status=ObservationStatus.PENDING.value,
                        created_at=utc_now(),
                    )
                )
            session.flush()
            plans = [self._rebuild_field(session, field, actor=actor) for field in sorted(fields)]
            audit(
                session,
                event_type="observations_submitted",
                reason="validated candidate profile observations",
                subject_type="profile",
                subject_id=None,
                actor=actor,
                after_ids=observation_ids,
                details={"fields": sorted(fields)},
            )
            result = {"observation_ids": observation_ids, "reconciliation": plans}
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def _candidates(self, session: Session, field_path: str) -> list[Candidate]:
        rows = session.execute(
            select(ObservationRow, SourceRow)
            .join(SourceRow, ObservationRow.source_id == SourceRow.id)
            .where(
                ObservationRow.field_path == field_path,
                ObservationRow.status != ObservationStatus.REJECTED.value,
            )
        ).all()
        return [
            Candidate(
                id=observation.id,
                field_path=observation.field_path,
                value=observation.typed_value,
                value_type=observation.value_type,
                source_id=observation.source_id,
                source_type=source.source_type,
                trust_class=source.trust_class,
                confidence=observation.extraction_confidence,
                effective_from=observation.effective_from,
                effective_until=observation.effective_until,
                observed_at=observation.observed_at,
                source_locator=source.source_locator,
            )
            for observation, source in rows
        ]

    def _rebuild_field(self, session: Session, field_path: str, *, actor: str) -> dict[str, Any]:
        resolved = session.execute(
            select(HumanResolutionRow, ReviewItemRow)
            .join(ReviewItemRow, HumanResolutionRow.review_item_id == ReviewItemRow.id)
            .where(
                ReviewItemRow.subject_ref == field_path,
                ReviewItemRow.status == ReviewStatus.RESOLVED.value,
            )
            .order_by(HumanResolutionRow.resolved_at.desc())
        ).first()
        apply_resolution = False
        if resolved and resolved[0].action in {"enter", "select"}:
            resolution, review = resolved
            if resolution.scope == "permanent_until_user_change":
                apply_resolution = True
            elif resolution.scope == "until_newer_evidence":
                newer_observation = session.scalar(
                    select(ObservationRow.id).where(
                        ObservationRow.field_path == field_path,
                        ObservationRow.created_at > resolution.resolved_at,
                    )
                )
                apply_resolution = newer_observation is None
            elif resolution.scope == "fixed_interval":
                now = utc_now()
                effective_from = resolution.effective_from
                effective_until = resolution.effective_until
                if effective_from and effective_from.tzinfo is None:
                    effective_from = effective_from.replace(tzinfo=now.tzinfo)
                if effective_until and effective_until.tzinfo is None:
                    effective_until = effective_until.replace(tzinfo=now.tzinfo)
                apply_resolution = bool(
                    effective_from and effective_until and effective_from <= now < effective_until
                )
            if not apply_resolution:
                for candidate_id in review.candidate_ids:
                    restored = session.get(ObservationRow, candidate_id)
                    if restored and restored.status == ObservationStatus.REJECTED.value:
                        restored.status = ObservationStatus.PENDING.value
        if resolved and apply_resolution:
            resolution = resolved[0]
            if resolution.action == "select":
                selected = session.get(ObservationRow, resolution.selected_candidate_id)
                if selected is None:
                    raise ValueError("Resolved profile candidate no longer exists")
                selected_value = selected.typed_value
                value_type = selected.value_type
                confidence = selected.extraction_confidence
                selected_ids = [selected.id]
            else:
                selected_value = resolution.entered_value
                value_type = "json"
                confidence = 1.0
                selected_ids = []
            existing = session.scalar(
                select(CanonicalFactRow).where(CanonicalFactRow.field_path == field_path)
            )
            now = utc_now()
            if existing is None:
                existing = CanonicalFactRow(
                    id=new_id(),
                    field_path=field_path,
                    typed_value=selected_value,
                    value_type=value_type,
                    verification_status="accepted",
                    confidence=confidence,
                    effective_from=resolution.effective_from,
                    effective_until=resolution.effective_until,
                    selected_observation_ids=selected_ids,
                    resolution_id=resolution.id,
                    projection_version=1,
                    updated_at=now,
                )
                session.add(existing)
            else:
                changed = (
                    existing.typed_value != selected_value
                    or existing.selected_observation_ids != selected_ids
                )
                existing.typed_value = selected_value
                existing.value_type = value_type
                existing.verification_status = "accepted"
                existing.confidence = confidence
                existing.effective_from = resolution.effective_from
                existing.effective_until = resolution.effective_until
                existing.selected_observation_ids = selected_ids
                existing.resolution_id = resolution.id
                existing.projection_version += int(changed)
                existing.updated_at = now
            return {
                "field_path": field_path,
                "status": "accepted",
                "fact_id": existing.id,
                "projection_version": existing.projection_version,
            }
        candidates = self._candidates(session, field_path)
        if not candidates:
            return {"field_path": field_path, "status": "missing"}
        plan = reconcile_field(candidates)
        existing = session.scalar(
            select(CanonicalFactRow).where(CanonicalFactRow.field_path == field_path)
        )
        current_version = existing.projection_version if existing else 0
        now = utc_now()
        if plan.conflicted_ids:
            for candidate_id in plan.conflicted_ids:
                row = session.get(ObservationRow, candidate_id)
                if row:
                    row.status = ObservationStatus.CONFLICTED.value
            if existing:
                changed = existing.verification_status != "conflicted"
                existing.verification_status = "conflicted"
                existing.selected_observation_ids = list(plan.conflicted_ids)
                existing.projection_version += int(changed)
                existing.updated_at = now
                fact_id = existing.id
            else:
                fact_id = new_id()
                session.add(
                    CanonicalFactRow(
                        id=fact_id,
                        field_path=field_path,
                        typed_value={"conflicted": True},
                        value_type="conflict",
                        verification_status="conflicted",
                        confidence=0,
                        effective_from=None,
                        effective_until=None,
                        selected_observation_ids=list(plan.conflicted_ids),
                        resolution_id=None,
                        projection_version=current_version + 1,
                        updated_at=now,
                    )
                )
            review = session.scalar(
                select(ReviewItemRow).where(
                    ReviewItemRow.review_type == ReviewType.CONFLICT.value,
                    ReviewItemRow.subject_ref == field_path,
                    ReviewItemRow.status.in_(
                        [ReviewStatus.OPEN.value, ReviewStatus.DEFERRED.value]
                    ),
                )
            )
            if review:
                review.candidate_ids = list(plan.conflicted_ids)
                review.status = ReviewStatus.OPEN.value
                review.deferred_until = None
            else:
                review = ReviewItemRow(
                    id=new_id(),
                    review_type=ReviewType.CONFLICT.value,
                    subject_type="profile_field",
                    subject_ref=field_path,
                    severity="high",
                    candidate_ids=list(plan.conflicted_ids),
                    explanation=(
                        "Credible overlapping observations disagree; human resolution is required."
                    ),
                    downstream_impact={"blocks_apply": True},
                    status=ReviewStatus.OPEN.value,
                    resolved_at=None,
                    resolution_id=None,
                    deferred_until=None,
                    created_at=now,
                )
                session.add(review)
            audit(
                session,
                event_type="profile_conflict",
                reason=plan.reason,
                subject_type="profile_field",
                subject_id=field_path,
                actor=actor,
                after_ids=[fact_id, review.id],
                details={"candidate_ids": list(plan.conflicted_ids)},
            )
            return {"field_path": field_path, "status": "conflicted", "review_id": review.id}

        assert plan.selected_id is not None
        winner = next(candidate for candidate in candidates if candidate.id == plan.selected_id)
        for candidate in candidates:
            row = session.get(ObservationRow, candidate.id)
            if row:
                row.status = (
                    ObservationStatus.ACCEPTED.value
                    if candidate.id == plan.selected_id
                    else ObservationStatus.SUPERSEDED.value
                )
        changed = (
            existing is None
            or existing.typed_value != plan.selected_value
            or existing.verification_status not in {"accepted", "verified"}
        )
        if existing:
            existing.typed_value = plan.selected_value
            existing.value_type = winner.value_type
            existing.verification_status = (
                "verified" if winner.trust_class == "official" else "accepted"
            )
            existing.confidence = plan.selected_confidence
            existing.effective_from = winner.effective_from
            existing.effective_until = winner.effective_until
            existing.selected_observation_ids = [winner.id]
            existing.resolution_id = None
            existing.projection_version += int(changed)
            existing.updated_at = now
            fact = existing
        else:
            fact = CanonicalFactRow(
                id=new_id(),
                field_path=field_path,
                typed_value=plan.selected_value,
                value_type=winner.value_type,
                verification_status="verified" if winner.trust_class == "official" else "accepted",
                confidence=plan.selected_confidence,
                effective_from=winner.effective_from,
                effective_until=winner.effective_until,
                selected_observation_ids=[winner.id],
                resolution_id=None,
                projection_version=1,
                updated_at=now,
            )
            session.add(fact)
        open_reviews = session.scalars(
            select(ReviewItemRow).where(
                ReviewItemRow.review_type == ReviewType.CONFLICT.value,
                ReviewItemRow.subject_ref == field_path,
                ReviewItemRow.status.in_([ReviewStatus.OPEN.value, ReviewStatus.DEFERRED.value]),
            )
        ).all()
        for review in open_reviews:
            review.status = ReviewStatus.DISMISSED.value
            review.resolved_at = now
        if changed:
            audit(
                session,
                event_type="canonical_fact_changed",
                reason=plan.reason,
                subject_type="canonical_fact",
                subject_id=fact.id,
                actor=actor,
                after_ids=[fact.id, winner.id],
                details={"field_path": field_path},
            )
        return {
            "field_path": field_path,
            "status": fact.verification_status,
            "fact_id": fact.id,
            "projection_version": fact.projection_version,
        }

    def get_current(self) -> list[dict[str, Any]]:
        with self.context.database.transaction() as session:
            rows = session.scalars(
                select(CanonicalFactRow).order_by(CanonicalFactRow.field_path)
            ).all()
            return [self._fact_dict(row) for row in rows]

    def get_fact(self, field_path: str) -> dict[str, Any] | None:
        with self.context.database.transaction() as session:
            row = session.scalar(
                select(CanonicalFactRow).where(CanonicalFactRow.field_path == field_path)
            )
            return self._fact_dict(row) if row else None

    @staticmethod
    def _fact_dict(row: CanonicalFactRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "field_path": row.field_path,
            "value": row.typed_value,
            "verification_status": row.verification_status,
            "confidence": row.confidence,
            "selected_observation_ids": row.selected_observation_ids,
            "projection_version": row.projection_version,
        }

    def list_reviews(self, status: ReviewStatus = ReviewStatus.OPEN) -> list[dict[str, Any]]:
        with self.context.database.transaction() as session:
            rows = session.scalars(
                select(ReviewItemRow)
                .where(ReviewItemRow.status == status.value)
                .order_by(ReviewItemRow.created_at)
            ).all()
            return [self._review_dict(row) for row in rows]

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with self.context.database.transaction() as session:
            row = session.get(ReviewItemRow, review_id)
            return self._review_dict(row) if row else None

    @staticmethod
    def _review_dict(row: ReviewItemRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "review_type": row.review_type,
            "subject": row.subject_ref,
            "severity": row.severity,
            "candidate_ids": row.candidate_ids,
            "explanation": row.explanation,
            "downstream_impact": row.downstream_impact,
            "status": row.status,
            "deferred_until": row.deferred_until,
        }

    def defer_review(self, review_id: str, until: datetime) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            review = session.get(ReviewItemRow, review_id)
            if review is None or review.status != ReviewStatus.OPEN.value:
                raise ValueError("Open review item not found")
            review.status = ReviewStatus.DEFERRED.value
            review.deferred_until = until
            audit(
                session,
                event_type="review_deferred",
                reason="user deferred review",
                subject_type="review",
                subject_id=review.id,
                actor="user",
            )
            return self._review_dict(review)

    def resolve_review(
        self,
        review_id: str,
        value: ResolutionInput,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "profile.resolve_review"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            review = session.get(ReviewItemRow, review_id)
            if review is None or review.status not in {
                ReviewStatus.OPEN.value,
                ReviewStatus.DEFERRED.value,
            }:
                raise ValueError("Resolvable review item not found")
            if review.subject_type != "profile_field" and value.action != "dismiss":
                raise ValueError(
                    "Connector and source failures require recovery or explicit dismissal"
                )
            resolution_id = new_id()
            now = utc_now()
            resolution = HumanResolutionRow(
                id=resolution_id,
                review_item_id=review.id,
                action=value.action,
                selected_candidate_id=value.selected_candidate_id,
                entered_value=value.entered_value,
                alternatives_considered=value.alternatives_considered,
                note=value.note,
                effective_from=value.effective_from,
                effective_until=value.effective_until,
                scope=value.scope,
                resolved_by=value.resolved_by,
                resolved_at=now,
            )
            session.add(resolution)
            if value.action == "select":
                candidate = session.get(ObservationRow, value.selected_candidate_id)
                if candidate is None or candidate.id not in review.candidate_ids:
                    raise ValueError("Selected candidate does not belong to this review")
                selected_value = candidate.typed_value
                selected_ids = [candidate.id]
                value_type = candidate.value_type
                confidence = candidate.extraction_confidence
            elif value.action == "enter":
                selected_value = value.entered_value
                selected_ids = []
                value_type = "json"
                confidence = 1.0
            elif value.action in {"dismiss", "contextual"}:
                review.status = ReviewStatus.DISMISSED.value
                review.resolved_at = now
                review.resolution_id = resolution_id
                early_result: dict[str, Any] = {
                    "review_id": review.id,
                    "status": review.status,
                }
                store_idempotent(session, idempotency_key, operation, early_result)
                return early_result
            else:
                raise ValueError("Unsupported resolution action")
            fact = session.scalar(
                select(CanonicalFactRow).where(CanonicalFactRow.field_path == review.subject_ref)
            )
            if fact is None:
                fact = CanonicalFactRow(
                    id=new_id(),
                    field_path=review.subject_ref,
                    typed_value=selected_value,
                    value_type=value_type,
                    verification_status="accepted",
                    confidence=confidence,
                    effective_from=value.effective_from,
                    effective_until=value.effective_until,
                    selected_observation_ids=selected_ids,
                    resolution_id=resolution_id,
                    projection_version=1,
                    updated_at=now,
                )
                session.add(fact)
            else:
                fact.typed_value = selected_value
                fact.value_type = value_type
                fact.verification_status = "accepted"
                fact.confidence = confidence
                fact.effective_from = value.effective_from
                fact.effective_until = value.effective_until
                fact.selected_observation_ids = selected_ids
                fact.resolution_id = resolution_id
                fact.projection_version += 1
                fact.updated_at = now
            for candidate_id in review.candidate_ids:
                candidate = session.get(ObservationRow, candidate_id)
                if candidate:
                    candidate.status = (
                        ObservationStatus.ACCEPTED.value
                        if candidate_id in selected_ids
                        else ObservationStatus.REJECTED.value
                    )
            review.status = ReviewStatus.RESOLVED.value
            review.resolved_at = now
            review.resolution_id = resolution_id
            session.flush()
            self._rebuild_field(session, review.subject_ref, actor=value.resolved_by)
            audit(
                session,
                event_type="review_resolved",
                reason=value.note or "explicit human resolution",
                subject_type="profile_field",
                subject_id=review.subject_ref,
                actor=value.resolved_by,
                after_ids=[resolution_id, fact.id],
                details={"review_id": review.id},
            )
            result = {
                "review_id": review.id,
                "status": review.status,
                "resolution_id": resolution_id,
                "fact": self._fact_dict(fact),
                "reevaluation_required": True,
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def rebuild_projection(self) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            fields = session.scalars(select(ObservationRow.field_path).distinct()).all()
            results = [
                self._rebuild_field(session, field, actor="system_rebuild") for field in fields
            ]
            audit(
                session,
                event_type="projection_rebuilt",
                reason="explicit deterministic rebuild",
                subject_type="profile",
                subject_id=None,
                details={"field_count": len(fields)},
            )
            return {"fields": results, "count": len(results)}

    def projection_version(self, session: Session | None = None) -> int:
        if session is not None:
            return int(session.scalar(select(func.max(CanonicalFactRow.projection_version))) or 0)
        with self.context.database.transaction() as owned:
            return int(owned.scalar(select(func.max(CanonicalFactRow.projection_version))) or 0)

    def get_dependencies(self, field_paths: list[str]) -> dict[str, list[str]]:
        from opportunityos.infrastructure.database import RequirementRow

        with self.context.database.transaction() as session:
            rows = session.scalars(
                select(RequirementRow).where(
                    RequirementRow.field_path.in_(field_paths),
                    RequirementRow.status != "superseded",
                )
            ).all()
            result: dict[str, list[str]] = {field: [] for field in field_paths}
            for row in rows:
                result.setdefault(row.field_path, []).append(row.opportunity_id)
            return {key: sorted(set(value)) for key, value in result.items()}

    def sync_status(self) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            latest_github = session.scalar(
                select(SourceRow)
                .where(SourceRow.source_type == SourceType.GITHUB_API.value)
                .order_by(SourceRow.retrieved_at.desc())
            )
            return {
                "projection_version": self.projection_version(session),
                "fact_count": int(
                    session.scalar(select(func.count()).select_from(CanonicalFactRow)) or 0
                ),
                "open_review_count": int(
                    session.scalar(
                        select(func.count())
                        .select_from(ReviewItemRow)
                        .where(ReviewItemRow.status == ReviewStatus.OPEN.value)
                    )
                    or 0
                ),
                "github_last_sync": latest_github.retrieved_at if latest_github else None,
            }

    def import_chatgpt_snapshot(
        self, snapshot: dict[str, Any], *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        facts = snapshot.get("facts")
        if snapshot.get("export_version") != "1.0" or not isinstance(facts, list):
            raise ValueError("Unsupported ChatGPT profile snapshot schema")
        generated_at = datetime.fromisoformat(str(snapshot["generated_at"]).replace("Z", "+00:00"))
        source = SourceCreate(
            source_type=SourceType.CHATGPT_SNAPSHOT,
            source_locator="local:chatgpt-profile-snapshot",
            display_name="ChatGPT profile snapshot",
            official_status=OfficialStatus.UNOFFICIAL,
            retrieved_at=utc_now(),
            published_at=generated_at,
            content_hash=__import__("hashlib")
            .sha256(__import__("json").dumps(snapshot, sort_keys=True).encode())
            .hexdigest(),
            mime_type="application/json",
            trust_class="candidate",
            metadata={"export_version": "1.0"},
        )
        source_id = self.add_source(
            source, f"{idempotency_key}:source" if idempotency_key else None
        )
        observations = [
            ObservationInput(
                field_path=str(item["field_path"]),
                value=item["value"],
                assertion_kind="reported",
                source_id=source_id,
                evidence_locator=str(item.get("supporting_text", "snapshot fact")),
                extraction_confidence=float(item.get("confidence", 0.5)),
                effective_from=datetime.fromisoformat(
                    str(item["effective_from"]).replace("Z", "+00:00")
                )
                if item.get("effective_from")
                else None,
                observed_at=generated_at,
                extractor_model=None,
            )
            for item in facts
        ]
        return self.submit_observations(
            observations, idempotency_key=idempotency_key, actor="chatgpt_snapshot_import"
        )

    def sync_github(
        self,
        username: str,
        *,
        token: str | None = None,
        client: GitHubClient | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        adapter = client or GitHubClient(token or os.environ.get("GITHUB_TOKEN"))
        try:
            evidence = adapter.repository_evidence(username)
        except GitHubAuthRequiredError:
            operation = "profile.github_auth_failure"
            with self.context.database.transaction() as session:
                previous = idempotent_result(session, idempotency_key, operation)
                if previous:
                    return previous
                existing = session.scalar(
                    select(ReviewItemRow).where(
                        ReviewItemRow.review_type == ReviewType.AUTH_FAILURE.value,
                        ReviewItemRow.subject_ref == f"github:{username}",
                        ReviewItemRow.status.in_(
                            [ReviewStatus.OPEN.value, ReviewStatus.DEFERRED.value]
                        ),
                    )
                )
                if existing:
                    review_id = existing.id
                else:
                    review_id = new_id()
                    session.add(
                        ReviewItemRow(
                            id=review_id,
                            review_type=ReviewType.AUTH_FAILURE.value,
                            subject_type="github_connector",
                            subject_ref=f"github:{username}",
                            severity="high",
                            candidate_ids=[],
                            explanation=(
                                "GitHub authentication is required or expired; no metadata "
                                "was imported."
                            ),
                            downstream_impact={"connector_blocked": True},
                            status=ReviewStatus.OPEN.value,
                            resolved_at=None,
                            resolution_id=None,
                            deferred_until=None,
                            created_at=utc_now(),
                        )
                    )
                audit(
                    session,
                    event_type="github_authentication_failed",
                    reason="GitHub adapter stopped after one authentication failure",
                    subject_type="github_connector",
                    subject_id=username,
                    after_ids=[review_id],
                )
                result = {
                    "auth_failure": True,
                    "review_id": review_id,
                    "next_step": "Run `gh auth login` or update the private GitHub token.",
                    "observations_imported": 0,
                }
                store_idempotent(session, idempotency_key, operation, result)
                return result
        serialized = [
            {"field_path": item.field_path, "value": item.value, "url": item.evidence_url}
            for item in evidence
        ]
        repository_count = sum(
            item.field_path.startswith("github.repositories.")
            and item.field_path.endswith(".exists")
            for item in evidence
        )
        merged_pull_request_count = sum(
            item.field_path.startswith("github.merged_pull_requests.")
            and item.field_path.endswith(".exists")
            for item in evidence
        )
        release_count = sum(
            item.field_path.startswith("github.repositories.")
            and ".releases." in item.field_path
            and item.field_path.endswith(".exists")
            for item in evidence
        )
        source = SourceCreate(
            source_type=SourceType.GITHUB_API,
            source_locator=f"https://api.github.com/users/{username}/repos",
            display_name=f"GitHub metadata for {username}",
            official_status=OfficialStatus.OFFICIAL,
            retrieved_at=utc_now(),
            content_hash=__import__("hashlib")
            .sha256(__import__("json").dumps(serialized, sort_keys=True, default=str).encode())
            .hexdigest(),
            mime_type="application/json",
            trust_class="official",
            metadata={
                "username": username,
                "repository_count": repository_count,
                "merged_pull_request_count": merged_pull_request_count,
                "release_count": release_count,
            },
        )
        source_id = self.add_source(
            source, f"{idempotency_key}:source" if idempotency_key else None
        )
        observations = [
            ObservationInput(
                field_path=item.field_path,
                value=item.value,
                assertion_kind="observed",
                source_id=source_id,
                evidence_locator=item.evidence_url,
                extraction_confidence=1.0,
                observed_at=utc_now(),
                extractor_model=None,
            )
            for item in evidence
        ]
        result = self.submit_observations(
            observations, idempotency_key=idempotency_key, actor="github_sync"
        )
        result["source_id"] = source_id
        result["repository_count"] = repository_count
        result["merged_pull_request_count"] = merged_pull_request_count
        result["release_count"] = release_count
        result["expertise_claims_created"] = 0
        with self.context.database.transaction() as session:
            recovered = session.scalars(
                select(ReviewItemRow).where(
                    ReviewItemRow.review_type == ReviewType.AUTH_FAILURE.value,
                    ReviewItemRow.subject_ref == f"github:{username}",
                    ReviewItemRow.status.in_(
                        [ReviewStatus.OPEN.value, ReviewStatus.DEFERRED.value]
                    ),
                )
            ).all()
            for review in recovered:
                review.status = ReviewStatus.DISMISSED.value
                review.resolved_at = utc_now()
        return result
