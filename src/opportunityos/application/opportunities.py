"""Opportunity sources, normalized records, requirements, and safe intake interface."""

from __future__ import annotations

import hashlib
from datetime import UTC
from pathlib import Path
from typing import Any

from sqlalchemy import select

from opportunityos.adapters.files import DocumentExtractor
from opportunityos.adapters.web import SafeWebRetriever, WebDocument
from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.application.profile import ProfileService
from opportunityos.domain.intake import normalize_url, semantic_key
from opportunityos.infrastructure.database import (
    ApplicationRow,
    OpportunityRow,
    RequirementRow,
    ReviewItemRow,
    SourceRow,
)
from opportunityos.schemas import (
    LifecycleState,
    OpportunityInput,
    RequirementInput,
    ReviewStatus,
    ReviewType,
    SourceCreate,
    SourceType,
)
from opportunityos.util import new_id, utc_now


class OpportunityService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context
        self.profiles = ProfileService(context)

    def add_source(self, value: SourceCreate, idempotency_key: str | None = None) -> str:
        return self.profiles.add_source(value, idempotency_key)

    def record_extraction_failure(self, reference: str, *, idempotency_key: str) -> str:
        """Persist one safe review item after a structured-output repair has failed."""
        operation = "opportunity.record_extraction_failure"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return str(previous["review_id"])
            review_id = new_id()
            session.add(
                ReviewItemRow(
                    id=review_id,
                    review_type=ReviewType.SOURCE_FAILURE.value,
                    subject_type="opportunity_extraction",
                    subject_ref=reference,
                    severity="high",
                    candidate_ids=[],
                    explanation=(
                        "Structured extraction remained invalid after one repair attempt."
                    ),
                    downstream_impact={"blocks_apply": True},
                    status=ReviewStatus.OPEN.value,
                    resolved_at=None,
                    resolution_id=None,
                    deferred_until=None,
                    created_at=utc_now(),
                )
            )
            audit(
                session,
                event_type="opportunity_extraction_failed",
                reason="schema validation failed after one bounded repair attempt",
                subject_type="opportunity_extraction",
                subject_id=reference,
                after_ids=[review_id],
            )
            store_idempotent(session, idempotency_key, operation, {"review_id": review_id})
            return review_id

    def ingest_file(self, path: Path, *, idempotency_key: str | None = None) -> dict[str, Any]:
        extracted = DocumentExtractor(self.context.settings, self.context.storage).ingest(path)
        source = SourceCreate(
            source_type=SourceType.LOCAL_DOCUMENT,
            source_locator=f"private:{extracted.content_hash}",
            display_name=path.name,
            retrieved_at=utc_now(),
            content_hash=extracted.content_hash,
            mime_type=extracted.mime_type,
            local_artifact_path=str(extracted.private_path),
            trust_class="candidate",
            metadata={"page_count": extracted.page_count, "needs_vision": extracted.needs_vision},
        )
        source_id = self.add_source(source, idempotency_key)
        return {
            "source_id": source_id,
            "mime_type": extracted.mime_type,
            "text": extracted.text,
            "needs_vision": extracted.needs_vision,
            "content_hash": extracted.content_hash,
        }

    def ingest_text(
        self, text: str, *, locator: str = "manual:text", idempotency_key: str | None = None
    ) -> dict[str, Any]:
        if not text.strip() or len(text) > 1_000_000:
            raise ValueError("Text input is empty or exceeds the configured limit")
        content = text.encode("utf-8")
        source = SourceCreate(
            source_type=SourceType.USER_STATEMENT,
            source_locator=locator,
            display_name="Manual opportunity text",
            retrieved_at=utc_now(),
            content_hash=hashlib.sha256(content).hexdigest(),
            mime_type="text/plain",
            trust_class="candidate",
            metadata={"requires_structured_extraction": True},
        )
        source_id = self.add_source(source, idempotency_key)
        return {
            "source_id": source_id,
            "text": text,
            "needs_structured_extraction": True,
            "source_instructions_trusted": False,
        }

    def ingest_url(
        self,
        url: str,
        *,
        retriever: SafeWebRetriever | None = None,
        official: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        adapter = retriever or SafeWebRetriever(self.context.settings)
        document: WebDocument = adapter.retrieve(url)
        source = SourceCreate(
            source_type=(
                SourceType.OFFICIAL_WEBPAGE if official else SourceType.UNOFFICIAL_WEBPAGE
            ),
            source_locator=document.final_url,
            display_name=document.final_url,
            official_status=("official" if official else "unofficial"),
            retrieved_at=utc_now(),
            content_hash=hashlib.sha256(document.content).hexdigest(),
            mime_type=document.mime_type,
            trust_class="official" if official else "candidate",
            metadata={
                "original_url": document.original_url,
                "final_url": document.final_url,
                "injection_signal_count": len(document.injection_signals),
            },
        )
        source_id = self.add_source(source, idempotency_key)
        if document.injection_signals:
            with self.context.database.transaction() as session:
                audit(
                    session,
                    event_type="prompt_injection_detected",
                    reason="untrusted source contained instruction-like content",
                    subject_type="source",
                    subject_id=source_id,
                    after_ids=[source_id],
                    details={"signal_count": len(document.injection_signals)},
                )
        return {
            "source_id": source_id,
            "original_url": document.original_url,
            "final_url": document.final_url,
            "text": document.text,
            "injection_detected": bool(document.injection_signals),
            "needs_structured_extraction": True,
            "source_instructions_trusted": False,
        }

    def reverify(
        self,
        opportunity_id: str,
        *,
        retriever: SafeWebRetriever | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve an opportunity's canonical URL and attach its current official evidence."""
        operation = "opportunity.reverify"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None or not opportunity.canonical_url:
                raise ValueError("Opportunity with a canonical official URL was not found")
            if opportunity.lifecycle_state in {
                LifecycleState.SUBMITTED.value,
                LifecycleState.FOLLOW_UP_DUE.value,
                LifecycleState.ACCEPTED.value,
                LifecycleState.REJECTED.value,
                LifecycleState.WITHDRAWN.value,
                LifecycleState.EXPIRED.value,
                LifecycleState.ARCHIVED.value,
            }:
                raise ValueError("Submitted or closed opportunities cannot be reverified")
            canonical_url = opportunity.canonical_url

        try:
            retrieved = self.ingest_url(
                canonical_url,
                retriever=retriever,
                official=True,
                idempotency_key=f"{idempotency_key}:source" if idempotency_key else None,
            )
        except Exception as error:
            with self.context.database.transaction() as session:
                previous = idempotent_result(session, idempotency_key, operation)
                if previous:
                    return previous
                opportunity = session.get(OpportunityRow, opportunity_id)
                if opportunity is None:
                    raise ValueError("Opportunity not found") from error
                existing = session.scalar(
                    select(ReviewItemRow).where(
                        ReviewItemRow.review_type == ReviewType.SOURCE_FAILURE.value,
                        ReviewItemRow.subject_type == "opportunity",
                        ReviewItemRow.subject_ref == opportunity_id,
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
                            review_type=ReviewType.SOURCE_FAILURE.value,
                            subject_type="opportunity",
                            subject_ref=opportunity_id,
                            severity="high",
                            candidate_ids=list(opportunity.source_ids),
                            explanation=(
                                "The canonical official page could not be reverified; prior "
                                "opportunity data was retained."
                            ),
                            downstream_impact={"blocks_apply": True},
                            status=ReviewStatus.OPEN.value,
                            resolved_at=None,
                            resolution_id=None,
                            deferred_until=None,
                            created_at=utc_now(),
                        )
                    )
                state_changed = (
                    opportunity.last_verified_at is not None
                    or opportunity.lifecycle_state != LifecycleState.REVIEW_REQUIRED.value
                )
                opportunity.last_verified_at = None
                opportunity.lifecycle_state = LifecycleState.REVIEW_REQUIRED.value
                opportunity.version += int(state_changed)
                opportunity.updated_at = utc_now()
                application = session.scalar(
                    select(ApplicationRow).where(ApplicationRow.opportunity_id == opportunity_id)
                )
                if application:
                    application.state = LifecycleState.PREPARING.value
                    application.updated_at = utc_now()
                audit(
                    session,
                    event_type="opportunity_reverification_failed",
                    reason="canonical official retrieval failed safely",
                    subject_type="opportunity",
                    subject_id=opportunity_id,
                    after_ids=[review_id],
                    details={"failure_type": type(error).__name__},
                )
                result = {
                    "opportunity_id": opportunity_id,
                    "verified": False,
                    "review_id": review_id,
                    "retry_allowed": True,
                    "requirements_reconciliation_required": False,
                }
                store_idempotent(session, idempotency_key, operation, result)
                return result
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            opportunity = session.get(OpportunityRow, opportunity_id)
            source = session.get(SourceRow, str(retrieved["source_id"]))
            if opportunity is None or source is None:
                raise ValueError("Reverification state could not be persisted")
            prior_sources = session.scalars(
                select(SourceRow).where(
                    SourceRow.id.in_(opportunity.source_ids), SourceRow.id != source.id
                )
            ).all()
            prior_official_hashes = {
                item.content_hash
                for item in prior_sources
                if item.official_status == "official"
                and item.source_type == SourceType.OFFICIAL_WEBPAGE.value
            }
            content_changed = (
                not prior_official_hashes or source.content_hash not in prior_official_hashes
            )
            opportunity.source_ids = sorted(set(opportunity.source_ids) | {source.id})
            opportunity.last_verified_at = source.retrieved_at
            recovered_reviews = session.scalars(
                select(ReviewItemRow).where(
                    ReviewItemRow.review_type == ReviewType.SOURCE_FAILURE.value,
                    ReviewItemRow.subject_type == "opportunity",
                    ReviewItemRow.subject_ref == opportunity_id,
                    ReviewItemRow.status.in_(
                        [ReviewStatus.OPEN.value, ReviewStatus.DEFERRED.value]
                    ),
                )
            ).all()
            for review in recovered_reviews:
                review.status = ReviewStatus.DISMISSED.value
                review.resolved_at = utc_now()
            if content_changed:
                opportunity.version += 1
                opportunity.source_completeness = 0
                opportunity.lifecycle_state = LifecycleState.REVIEW_REQUIRED.value
                for requirement in session.scalars(
                    select(RequirementRow).where(
                        RequirementRow.opportunity_id == opportunity_id,
                        RequirementRow.status != "superseded",
                    )
                ).all():
                    requirement.status = "superseded"
                application = session.scalar(
                    select(ApplicationRow).where(ApplicationRow.opportunity_id == opportunity_id)
                )
                if application:
                    application.state = LifecycleState.PREPARING.value
                    application.updated_at = utc_now()
            opportunity.updated_at = utc_now()
            audit(
                session,
                event_type="opportunity_reverified",
                reason="canonical official source retrieved and compared",
                subject_type="opportunity",
                subject_id=opportunity_id,
                after_ids=[opportunity_id, source.id],
                details={"content_changed": content_changed},
            )
            result = {
                **retrieved,
                "opportunity_id": opportunity_id,
                "verified": True,
                "content_changed": content_changed,
                "requirements_reconciliation_required": content_changed,
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def submit_opportunity(
        self, value: OpportunityInput, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        operation = "opportunity.submit"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            sources = session.scalars(
                select(SourceRow).where(SourceRow.id.in_(value.source_ids))
            ).all()
            if len({source.id for source in sources}) != len(set(value.source_ids)):
                raise ValueError("One or more source identifiers are unknown")
            family_key, entity_key = semantic_key(
                value.organization, value.canonical_title, value.cycle
            )
            canonical_url = normalize_url(str(value.canonical_url)) if value.canonical_url else None
            existing = session.scalar(
                select(OpportunityRow).where(
                    (OpportunityRow.entity_key == entity_key)
                    | (
                        (OpportunityRow.canonical_url == canonical_url)
                        if canonical_url
                        else (OpportunityRow.id == "")
                    )
                )
            )
            now = utc_now()
            official_sources = [
                source
                for source in sources
                if source.official_status == "official"
                and source.source_type == SourceType.OFFICIAL_WEBPAGE.value
            ]
            official = bool(official_sources)
            official_verified_at = (
                max(
                    (source.retrieved_at for source in official_sources),
                    key=lambda value: value.replace(tzinfo=value.tzinfo or UTC),
                )
                if official_sources
                else None
            )
            if existing:
                existing.source_ids = sorted(set(existing.source_ids) | set(value.source_ids))
                if official:
                    existing.canonical_title = value.canonical_title
                    existing.organization = value.organization
                    existing.opportunity_type = value.opportunity_type
                    existing.canonical_url = canonical_url or existing.canonical_url
                    existing.application_url = (
                        normalize_url(str(value.application_url))
                        if value.application_url
                        else existing.application_url
                    )
                    existing.location = value.location
                    existing.delivery_mode = value.delivery_mode
                    existing.compensation_or_award = value.compensation_or_award
                    existing.deadline_at = value.deadline_at
                    existing.deadline_timezone = value.deadline_timezone
                    existing.open_status = value.open_status
                    existing.source_completeness = value.source_completeness
                    existing.last_verified_at = official_verified_at
                    if existing.lifecycle_state == LifecycleState.DISCOVERED.value:
                        existing.lifecycle_state = LifecycleState.SOURCE_VERIFIED.value
                existing.updated_at = now
                existing.version += 1
                result = {
                    "opportunity_id": existing.id,
                    "duplicate": True,
                    "source_count": len(existing.source_ids),
                }
            else:
                opportunity_id = new_id()
                row = OpportunityRow(
                    id=opportunity_id,
                    canonical_title=value.canonical_title,
                    organization=value.organization,
                    opportunity_type=value.opportunity_type,
                    cycle=value.cycle,
                    program_family_key=family_key,
                    entity_key=entity_key,
                    canonical_url=canonical_url,
                    application_url=normalize_url(str(value.application_url))
                    if value.application_url
                    else None,
                    location=value.location,
                    delivery_mode=value.delivery_mode,
                    compensation_or_award=value.compensation_or_award,
                    deadline_at=value.deadline_at,
                    deadline_timezone=value.deadline_timezone,
                    open_status=value.open_status,
                    last_verified_at=official_verified_at,
                    lifecycle_state=(
                        LifecycleState.SOURCE_VERIFIED.value
                        if official
                        else LifecycleState.DISCOVERED.value
                    ),
                    source_completeness=value.source_completeness,
                    source_ids=value.source_ids,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                result = {
                    "opportunity_id": opportunity_id,
                    "duplicate": False,
                    "source_count": len(value.source_ids),
                }
            audit(
                session,
                event_type="opportunity_submitted",
                reason="normalized candidate opportunity",
                subject_type="opportunity",
                subject_id=str(result["opportunity_id"]),
                after_ids=[str(result["opportunity_id"]), *value.source_ids],
                details={"duplicate": result["duplicate"]},
            )
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def submit_requirement(
        self, value: RequirementInput, *, idempotency_key: str | None = None
    ) -> str:
        operation = "opportunity.submit_requirement"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return str(previous["requirement_id"])
            opportunity = session.get(OpportunityRow, value.opportunity_id)
            if opportunity is None or session.get(SourceRow, value.source_id) is None:
                raise ValueError("Opportunity or source not found")
            if value.source_id not in opportunity.source_ids:
                raise ValueError("Requirement source is not attached to the opportunity")
            requirement_id = new_id()
            session.add(
                RequirementRow(
                    id=requirement_id,
                    opportunity_id=value.opportunity_id,
                    requirement_type=value.requirement_type,
                    field_path=value.field_path,
                    normalized_predicate={
                        "operator": value.operator.value,
                        "expected": value.expected,
                    },
                    hard_or_soft="hard" if value.hard else "soft",
                    extracted_text=value.extracted_text,
                    source_id=value.source_id,
                    evidence_locator=value.evidence_locator,
                    extraction_confidence=value.extraction_confidence,
                    status=value.status,
                    ruleset_version=value.ruleset_version,
                    created_at=utc_now(),
                )
            )
            opportunity.lifecycle_state = LifecycleState.PARSED.value
            opportunity.updated_at = utc_now()
            audit(
                session,
                event_type="requirement_submitted",
                reason="validated structured opportunity requirement",
                subject_type="opportunity",
                subject_id=opportunity.id,
                after_ids=[requirement_id],
                ruleset_version=value.ruleset_version,
            )
            store_idempotent(
                session, idempotency_key, operation, {"requirement_id": requirement_id}
            )
            return requirement_id

    def get(self, opportunity_id: str) -> dict[str, Any] | None:
        with self.context.database.transaction() as session:
            row = session.get(OpportunityRow, opportunity_id)
            if row is None:
                return None
            requirements = session.scalars(
                select(RequirementRow).where(RequirementRow.opportunity_id == row.id)
            ).all()
            return {
                "id": row.id,
                "title": row.canonical_title,
                "organization": row.organization,
                "type": row.opportunity_type,
                "cycle": row.cycle,
                "canonical_url": row.canonical_url,
                "application_url": row.application_url,
                "deadline_at": row.deadline_at,
                "open_status": row.open_status,
                "lifecycle_state": row.lifecycle_state,
                "source_ids": row.source_ids,
                "source_completeness": row.source_completeness,
                "version": row.version,
                "requirements": [
                    {
                        "id": item.id,
                        "type": item.requirement_type,
                        "field_path": item.field_path,
                        "predicate": item.normalized_predicate,
                        "hard": item.hard_or_soft == "hard",
                        "status": item.status,
                        "source_id": item.source_id,
                    }
                    for item in requirements
                ],
            }

    def find_duplicates(self, organization: str, title: str, cycle: str | None) -> list[str]:
        _, entity_key = semantic_key(organization, title, cycle)
        with self.context.database.transaction() as session:
            return list(
                session.scalars(
                    select(OpportunityRow.id).where(OpportunityRow.entity_key == entity_key)
                ).all()
            )
