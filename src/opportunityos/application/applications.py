"""Evidence-grounded private application packet interface."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from sqlalchemy import func, select

from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.domain.decisions import validate_transition
from opportunityos.infrastructure.database import (
    ApplicationArtifactRow,
    ApplicationRow,
    CanonicalFactRow,
    EvaluationRow,
    OpportunityRow,
    RequirementRow,
    SourceRow,
)
from opportunityos.schemas import ClaimInput, LifecycleState, OverallEligibility
from opportunityos.util import new_id, sha256_file, utc_now


class ApplicationService:
    REQUIRED_ARTIFACTS: ClassVar[set[str]] = {
        "decision_brief",
        "requirements_checklist",
        "evidence_map",
        "draft_answers",
        "resume_recommendations",
        "submission_checklist",
        "application_state",
    }

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def _packet_dir(self, application_id: str) -> Path:
        root = self.context.storage.category_path("applications")
        path = self.context.storage.require_private(root / application_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create(self, opportunity_id: str, *, idempotency_key: str | None = None) -> str:
        operation = "application.create"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return str(previous["application_id"])
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None:
                raise ValueError("Opportunity not found")
            existing = session.scalar(
                select(ApplicationRow).where(ApplicationRow.opportunity_id == opportunity_id)
            )
            if existing:
                if opportunity.lifecycle_state in {
                    LifecycleState.EVALUATED.value,
                    LifecycleState.SHORTLISTED.value,
                }:
                    validate_transition(
                        LifecycleState(opportunity.lifecycle_state),
                        LifecycleState.PREPARING,
                    )
                    opportunity.lifecycle_state = LifecycleState.PREPARING.value
                    opportunity.updated_at = utc_now()
                store_idempotent(
                    session,
                    idempotency_key,
                    operation,
                    {"application_id": existing.id},
                )
                return existing.id
            application_id = new_id()
            now = utc_now()
            session.add(
                ApplicationRow(
                    id=application_id,
                    opportunity_id=opportunity_id,
                    state=LifecycleState.PREPARING.value,
                    official_application_url=opportunity.application_url,
                    started_at=now,
                    submitted_at=None,
                    outcome=None,
                    outcome_at=None,
                    follow_up_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            if opportunity.lifecycle_state in {
                LifecycleState.EVALUATED.value,
                LifecycleState.SHORTLISTED.value,
            }:
                validate_transition(
                    LifecycleState(opportunity.lifecycle_state), LifecycleState.PREPARING
                )
                opportunity.lifecycle_state = LifecycleState.PREPARING.value
                opportunity.updated_at = now
            audit(
                session,
                event_type="application_created",
                reason="explicit user preparation request",
                subject_type="application",
                subject_id=application_id,
                actor="user",
                after_ids=[application_id, opportunity_id],
            )
            store_idempotent(
                session, idempotency_key, operation, {"application_id": application_id}
            )
            return application_id

    def prepare(
        self,
        opportunity_id: str,
        claims: list[ClaimInput],
        *,
        generation_model: str | None = None,
        prompt_version: str = "1.0",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        application_id = self.create(
            opportunity_id, idempotency_key=f"{idempotency_key}:create" if idempotency_key else None
        )
        operation = "application.prepare"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            application = session.get(ApplicationRow, application_id)
            opportunity = session.get(OpportunityRow, opportunity_id)
            assert application is not None and opportunity is not None
            evaluation = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity_id)
                .order_by(EvaluationRow.created_at.desc())
            )
            if evaluation is None:
                raise ValueError("Opportunity must be evaluated before preparation")
            fact_ids = {fact_id for claim in claims for fact_id in claim.supporting_fact_ids}
            facts = session.scalars(
                select(CanonicalFactRow).where(CanonicalFactRow.id.in_(fact_ids))
            ).all()
            fact_map = {fact.id: fact for fact in facts}
            missing = sorted(fact_ids - set(fact_map))
            unsafe = sorted(
                fact.id
                for fact in facts
                if fact.verification_status not in {"verified", "accepted"}
            )
            ungrounded_claims = [
                index for index, claim in enumerate(claims) if not claim.supporting_fact_ids
            ]
            if missing or unsafe or ungrounded_claims:
                raise ValueError(
                    f"Grounding failed; missing={missing}, unsafe={unsafe}, "
                    f"claims_without_evidence={ungrounded_claims}"
                )
            requirements = session.scalars(
                select(RequirementRow).where(
                    RequirementRow.opportunity_id == opportunity_id,
                    RequirementRow.status != "superseded",
                )
            ).all()
            packet_dir = self._packet_dir(application_id)
            evidence_map = {
                "evaluation_id": evaluation.id,
                "profile_projection_version": evaluation.profile_projection_version,
                "opportunity_version": evaluation.opportunity_version,
                "claims": [
                    {
                        "claim": claim.text,
                        "status": claim.status,
                        "supporting_fact_ids": claim.supporting_fact_ids,
                    }
                    for claim in claims
                ],
                "facts": {
                    fact_id: {
                        "field_path": fact_map[fact_id].field_path,
                        "value": fact_map[fact_id].typed_value,
                        "verification_status": fact_map[fact_id].verification_status,
                    }
                    for fact_id in sorted(fact_map)
                },
            }
            files: dict[str, tuple[str, str]] = {
                "decision_brief": (
                    "decision_brief.txt",
                    (
                        f"{evaluation.decision_label.upper()} — {opportunity.canonical_title}\n"
                        f"Official source: {opportunity.canonical_url or 'Not verified'}\n"
                        f"Application: {opportunity.application_url or 'Not available'}\n"
                        f"Deadline: {opportunity.deadline_at or 'Unknown'}\n"
                        f"Net value: {evaluation.net_value_score:.2f}\n"
                        f"Confidence: {evaluation.decision_confidence:.2f}\n"
                        f"Risk: {evaluation.main_risk}\n"
                        "Next human step: review the evidence map and complete the manual "
                        "submission checklist.\n"
                    ),
                ),
                "requirements_checklist": (
                    "requirements_checklist.md",
                    "# Requirements checklist\n\n"
                    + "\n".join(
                        f"- [ ] {item.extracted_text} — source `{item.source_id}`"
                        for item in requirements
                    ),
                ),
                "evidence_map": (
                    "evidence_map.json",
                    json.dumps(evidence_map, indent=2, sort_keys=True, default=str),
                ),
                "draft_answers": (
                    "draft_answers.md",
                    "# Grounded draft claims\n\n"
                    + "\n\n".join(
                        f"## Claim {index + 1}\n\n{claim.text}\n\nEvidence: "
                        + ", ".join(f"`{fact_id}`" for fact_id in claim.supporting_fact_ids)
                        for index, claim in enumerate(claims)
                    )
                    + ("\n\n_No draft claims were supplied._" if not claims else ""),
                ),
                "resume_recommendations": (
                    "resume_recommendations.md",
                    "# Resume recommendations\n\nUse only the verified claims in "
                    "`evidence_map.json`. "
                    "Tailor ordering manually; OpportunityOS does not fabricate metrics.\n",
                ),
                "submission_checklist": (
                    "submission_checklist.md",
                    "# Manual submission checklist\n\n"
                    "- [ ] Re-open the official application link.\n"
                    "- [ ] Confirm the deadline and eligibility wording.\n"
                    "- [ ] Review every draft claim against its evidence ID.\n"
                    "- [ ] Upload and submit manually.\n"
                    "- [ ] Tell OpportunityOS when submission is complete.\n",
                ),
                "application_state": (
                    "application_state.json",
                    json.dumps(
                        {
                            "application_id": application_id,
                            "opportunity_id": opportunity_id,
                            "evaluation_id": evaluation.id,
                            "state": application.state,
                            "profile_projection_version": evaluation.profile_projection_version,
                            "opportunity_version": evaluation.opportunity_version,
                            "generated_at": utc_now().isoformat(),
                            "external_submission_performed": False,
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                ),
            }
            existing_artifacts = {
                row.artifact_type: row
                for row in session.scalars(
                    select(ApplicationArtifactRow).where(
                        ApplicationArtifactRow.application_id == application_id
                    )
                ).all()
            }
            artifact_ids: list[str] = []
            for artifact_type, (filename, content) in files.items():
                path = self.context.storage.require_private(packet_dir / filename)
                path.write_text(content, encoding="utf-8")
                existing_artifact = existing_artifacts.get(artifact_type)
                if existing_artifact:
                    existing_artifact.private_path = str(path)
                    existing_artifact.content_hash = sha256_file(path)
                    existing_artifact.supporting_fact_ids = sorted(fact_ids)
                    existing_artifact.generation_model = generation_model
                    existing_artifact.prompt_version = prompt_version
                    existing_artifact.user_approved = False
                    existing_artifact.created_at = utc_now()
                    artifact_ids.append(existing_artifact.id)
                    continue
                artifact_id = new_id()
                artifact_ids.append(artifact_id)
                session.add(
                    ApplicationArtifactRow(
                        id=artifact_id,
                        application_id=application_id,
                        artifact_type=artifact_type,
                        private_path=str(path),
                        content_hash=sha256_file(path),
                        supporting_fact_ids=sorted(fact_ids),
                        generation_model=generation_model,
                        prompt_version=prompt_version,
                        user_approved=False,
                        created_at=utc_now(),
                    )
                )
            application.updated_at = utc_now()
            audit(
                session,
                event_type="application_packet_prepared",
                reason="grounded private artifacts compiled",
                subject_type="application",
                subject_id=application_id,
                actor="hermes",
                after_ids=artifact_ids,
                details={"claim_count": len(claims), "external_action": False},
            )
            result = {
                "application_id": application_id,
                "packet_path": str(packet_dir),
                "artifact_types": sorted(files),
                "grounded_claim_count": len(claims),
                "state": application.state,
                "external_submission_performed": False,
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def prepare_context(self, opportunity_id: str) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None:
                raise ValueError("Opportunity not found")
            evaluation = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity_id)
                .order_by(EvaluationRow.created_at.desc())
            )
            facts = session.scalars(
                select(CanonicalFactRow).where(
                    CanonicalFactRow.verification_status.in_(["accepted", "verified"])
                )
            ).all()
            return {
                "opportunity": {
                    "id": opportunity.id,
                    "title": opportunity.canonical_title,
                    "official_url": opportunity.canonical_url,
                    "application_url": opportunity.application_url,
                    "deadline": opportunity.deadline_at,
                },
                "evaluation": {
                    "decision": evaluation.decision_label,
                    "risk": evaluation.main_risk,
                }
                if evaluation
                else None,
                "eligible_facts": [
                    {
                        "id": fact.id,
                        "field_path": fact.field_path,
                        "value": fact.typed_value,
                        "status": fact.verification_status,
                    }
                    for fact in facts
                ],
            }

    def mark_ready(self, application_id: str) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            application = session.get(ApplicationRow, application_id)
            if application is None:
                raise ValueError("Application not found")
            opportunity = session.get(OpportunityRow, application.opportunity_id)
            assert opportunity is not None
            evaluation = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity.id)
                .order_by(EvaluationRow.created_at.desc())
            )
            artifact_rows = session.scalars(
                select(ApplicationArtifactRow).where(
                    ApplicationArtifactRow.application_id == application_id
                )
            ).all()
            artifacts = {row.artifact_type: row for row in artifact_rows}
            problems: list[str] = []
            if not opportunity.application_url or not opportunity.canonical_url:
                problems.append("official source and application link are required")
            if opportunity.open_status not in {"open", "future"}:
                problems.append("official application is not verified open or future")
            official_sources = session.scalars(
                select(SourceRow).where(SourceRow.id.in_(opportunity.source_ids))
            ).all()
            last_verified = opportunity.last_verified_at
            if last_verified and last_verified.tzinfo is None:
                last_verified = last_verified.replace(tzinfo=UTC)
            if (
                not last_verified
                or last_verified < datetime.now(UTC) - timedelta(days=1)
                or not any(
                    source.official_status == "official"
                    and source.source_type == "official_webpage"
                    for source in official_sources
                )
            ):
                problems.append("a current official source verification is required")
            if opportunity.source_completeness < 1:
                problems.append("official requirements must be completely reconciled")
            if opportunity.deadline_at is None:
                problems.append("a verified future deadline is required")
            else:
                deadline = opportunity.deadline_at
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=UTC)
                if deadline <= datetime.now(UTC):
                    problems.append("deadline has passed")
            if (
                evaluation is None
                or evaluation.eligibility_summary.get("overall")
                != OverallEligibility.ELIGIBLE.value
            ):
                problems.append("current deterministic eligibility must be eligible")
            current_projection_version = int(
                session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0
            )
            if evaluation and (
                evaluation.profile_projection_version != current_projection_version
                or evaluation.opportunity_version != opportunity.version
            ):
                problems.append("evaluation inputs are stale; reevaluate before READY")
            missing = sorted(self.REQUIRED_ARTIFACTS - set(artifacts))
            if missing:
                problems.append(f"missing packet artifacts: {missing}")
            for artifact_type in sorted(self.REQUIRED_ARTIFACTS & set(artifacts)):
                artifact = artifacts[artifact_type]
                path = self.context.storage.require_private(Path(artifact.private_path))
                if not path.is_file() or sha256_file(path) != artifact.content_hash:
                    problems.append(f"artifact integrity failed: {artifact_type}")
            evidence_artifact = artifacts.get("evidence_map")
            if evidence_artifact:
                evidence_path = self.context.storage.require_private(
                    Path(evidence_artifact.private_path)
                )
                if evidence_path.is_file():
                    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                    if evaluation and evidence.get("evaluation_id") != evaluation.id:
                        problems.append("packet was generated from an older evaluation")
                    if any(
                        claim.get("status") == "needs_review"
                        for claim in evidence.get("claims", [])
                    ):
                        problems.append("all claims must be verified or user approved")
            if problems:
                raise ValueError("READY blocked: " + "; ".join(problems))
            validate_transition(LifecycleState(opportunity.lifecycle_state), LifecycleState.READY)
            application.state = LifecycleState.READY.value
            application.updated_at = utc_now()
            opportunity.lifecycle_state = LifecycleState.READY.value
            opportunity.updated_at = utc_now()
            audit(
                session,
                event_type="application_marked_ready",
                reason="official source, eligibility, deadline, and grounded artifacts verified",
                subject_type="application",
                subject_id=application.id,
                actor="user",
                after_ids=[application.id, opportunity.id],
            )
            return {"application_id": application.id, "state": application.state}

    def store_artifact(
        self,
        application_id: str,
        *,
        artifact_type: str,
        content: str,
        supporting_fact_ids: list[str],
        generation_model: str | None = None,
        prompt_version: str = "1.0",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "application.store_artifact"
        if not artifact_type or len(artifact_type) > 100 or not content or len(content) > 1_000_000:
            raise ValueError("Artifact type or content is invalid")
        if artifact_type in self.REQUIRED_ARTIFACTS:
            raise ValueError("Required packet artifacts can only be written by application.prepare")
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            application = session.get(ApplicationRow, application_id)
            if application is None:
                raise ValueError("Application not found")
            existing = session.scalar(
                select(ApplicationArtifactRow).where(
                    ApplicationArtifactRow.application_id == application_id,
                    ApplicationArtifactRow.artifact_type == artifact_type,
                )
            )
            if existing:
                raise ValueError("Artifact type already exists for this application")
            fact_ids = set(supporting_fact_ids)
            facts = session.scalars(
                select(CanonicalFactRow).where(CanonicalFactRow.id.in_(fact_ids))
            ).all()
            if (
                not fact_ids
                or set(fact.id for fact in facts) != fact_ids
                or any(fact.verification_status not in {"verified", "accepted"} for fact in facts)
            ):
                raise ValueError("Artifact references missing or unsafe canonical evidence")
            packet_dir = self._packet_dir(application_id)
            artifact_id = new_id()
            safe_type = "".join(
                char if char.isalnum() or char in "-_" else "_" for char in artifact_type
            )
            path = self.context.storage.require_private(
                packet_dir / f"{safe_type}-{artifact_id}.md"
            )
            path.write_text(content, encoding="utf-8")
            session.add(
                ApplicationArtifactRow(
                    id=artifact_id,
                    application_id=application_id,
                    artifact_type=artifact_type,
                    private_path=str(path),
                    content_hash=sha256_file(path),
                    supporting_fact_ids=sorted(fact_ids),
                    generation_model=generation_model,
                    prompt_version=prompt_version,
                    user_approved=False,
                    created_at=utc_now(),
                )
            )
            audit(
                session,
                event_type="application_artifact_stored",
                reason="validated grounded private artifact",
                subject_type="application",
                subject_id=application_id,
                actor="hermes",
                after_ids=[artifact_id],
            )
            result = {"artifact_id": artifact_id, "artifact_type": artifact_type}
            store_idempotent(session, idempotency_key, operation, result)
            return result
