from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from opportunityos.adapters.github import GitHubAuthRequiredError, GitHubEvidence
from opportunityos.application.profile import ProfileService
from opportunityos.schemas import (
    ObservationInput,
    OfficialStatus,
    ResolutionInput,
    ReviewStatus,
    SourceCreate,
    SourceType,
)


def _source(
    service: ProfileService, locator: str, *, source_type: SourceType = SourceType.LOCAL_DOCUMENT
) -> str:
    return service.add_source(
        SourceCreate(
            source_type=source_type,
            source_locator=locator,
            display_name=locator,
            official_status=OfficialStatus.UNKNOWN,
            retrieved_at=datetime.now(UTC),
            content_hash=(locator.encode().hex() + "0" * 64)[:64],
            mime_type="text/plain",
            trust_class="credible",
        )
    )


def _observation(source_id: str, value: Any, when: datetime) -> ObservationInput:
    return ObservationInput(
        field_path="education.expected_graduation",
        value=value,
        source_id=source_id,
        evidence_locator="synthetic fixture",
        extraction_confidence=0.9,
        effective_from=datetime(2026, 8, 1, tzinfo=UTC),
        observed_at=when,
    )


def test_conflict_resolution_and_rebuild(context_factory: Any) -> None:
    service = ProfileService(context_factory())
    now = datetime.now(UTC)
    first_source = _source(service, "synthetic-resume-a")
    second_source = _source(service, "synthetic-resume-b")
    service.submit_observations([_observation(first_source, "2027-05", now)])
    result = service.submit_observations(
        [_observation(second_source, "2028-05", now + timedelta(minutes=1))]
    )
    assert result["reconciliation"][0]["status"] == "conflicted"
    fact = service.get_fact("education.expected_graduation")
    assert fact and fact["verification_status"] == "conflicted"
    review = service.list_reviews()[0]
    assert service.get_review(review["id"])["subject"] == "education.expected_graduation"
    deferred = service.defer_review(review["id"], now + timedelta(days=1))
    assert deferred["status"] == "deferred"
    assert len(service.list_reviews(ReviewStatus.DEFERRED)) == 1
    selected = review["candidate_ids"][0]
    resolved = service.resolve_review(
        review["id"],
        ResolutionInput(
            action="select",
            selected_candidate_id=selected,
            alternatives_considered=review["candidate_ids"],
            note="Synthetic user resolution",
            scope="until_newer_evidence",
        ),
    )
    expected = resolved["fact"]["value"]
    fact_id = resolved["fact"]["id"]
    rebuilt = service.rebuild_projection()
    assert rebuilt["count"] == 1
    assert service.get_fact("education.expected_graduation")["value"] == expected
    assert service.get_fact("education.expected_graduation")["id"] == fact_id
    assert service.get_review("missing") is None
    assert service.sync_status()["fact_count"] == 1


def test_same_source_newer_value_supersedes(context_factory: Any) -> None:
    service = ProfileService(context_factory())
    source_id = _source(service, "synthetic-transcript")
    now = datetime.now(UTC)
    result = service.submit_observations(
        [
            ObservationInput(
                field_path="education.gpa",
                value=3.3,
                source_id=source_id,
                evidence_locator="old record",
                extraction_confidence=1,
                observed_at=now,
            ),
            ObservationInput(
                field_path="education.gpa",
                value=3.5,
                source_id=source_id,
                evidence_locator="new record",
                extraction_confidence=1,
                observed_at=now + timedelta(days=1),
            ),
        ]
    )
    assert result["reconciliation"][0]["status"] == "accepted"
    assert service.get_fact("education.gpa")["value"] == 3.5
    assert service.list_reviews() == []


def test_chatgpt_snapshot_is_candidate_source(context_factory: Any) -> None:
    service = ProfileService(context_factory())
    result = service.import_chatgpt_snapshot(
        {
            "export_version": "1.0",
            "generated_at": "2026-08-21T12:00:00Z",
            "facts": [
                {
                    "field_path": "career.objective",
                    "value": "AI research",
                    "confidence": 0.7,
                    "supporting_text": "Synthetic",
                }
            ],
        }
    )
    assert result["observation_ids"]
    assert service.get_fact("career.objective")["verification_status"] == "accepted"


class FakeGitHubClient:
    def repository_evidence(self, username: str) -> list[GitHubEvidence]:
        return [
            GitHubEvidence(
                field_path="github.repositories.synthetic.language",
                value="Rust",
                evidence_url=f"https://github.com/{username}/synthetic",
            )
        ]


class FailingGitHubClient:
    def repository_evidence(self, username: str) -> list[GitHubEvidence]:
        raise GitHubAuthRequiredError(f"synthetic auth failure for {username}")


def test_github_language_does_not_create_expertise(context_factory: Any) -> None:
    service = ProfileService(context_factory())
    result = service.sync_github("synthetic-user", client=FakeGitHubClient())  # type: ignore[arg-type]
    assert result["expertise_claims_created"] == 0
    assert service.get_fact("github.repositories.synthetic.language")["value"] == "Rust"
    assert service.get_fact("skills.rust_expert") is None


def test_github_auth_failure_creates_one_safe_review(context_factory: Any) -> None:
    service = ProfileService(context_factory())
    first = service.sync_github(
        "synthetic-user",
        client=FailingGitHubClient(),  # type: ignore[arg-type]
        idempotency_key="github-auth-failure",
    )
    second = service.sync_github(
        "synthetic-user",
        client=FailingGitHubClient(),  # type: ignore[arg-type]
        idempotency_key="github-auth-failure",
    )
    assert first == second
    assert first["auth_failure"] is True
    reviews = service.list_reviews()
    assert len(reviews) == 1
    assert reviews[0]["review_type"] == "auth_failure"
    with pytest.raises(ValueError, match="require recovery"):
        service.resolve_review(
            reviews[0]["id"],
            ResolutionInput(
                action="enter",
                entered_value="not a profile value",
                scope="until_newer_evidence",
            ),
        )
    recovered = service.sync_github(
        "synthetic-user",
        client=FakeGitHubClient(),  # type: ignore[arg-type]
        idempotency_key="github-auth-recovered",
    )
    assert "auth_failure" not in recovered
    assert service.list_reviews() == []


def test_entered_and_dismissed_human_resolutions(context_factory: Any) -> None:
    service = ProfileService(context_factory())
    now = datetime.now(UTC)
    first_source = _source(service, "synthetic-enter-a")
    second_source = _source(service, "synthetic-enter-b")
    service.submit_observations([_observation(first_source, "2027-05", now)])
    service.submit_observations(
        [_observation(second_source, "2028-05", now + timedelta(minutes=1))]
    )
    review = service.list_reviews()[0]
    entered = service.resolve_review(
        review["id"],
        ResolutionInput(
            action="enter",
            entered_value="2029-05",
            alternatives_considered=review["candidate_ids"],
            note="Synthetic corrected value",
            scope="permanent_until_user_change",
        ),
        idempotency_key="resolution-enter",
    )
    assert entered["fact"]["value"] == "2029-05"
    assert (
        service.resolve_review(
            review["id"],
            ResolutionInput(
                action="enter",
                entered_value="ignored by idempotency",
                scope="permanent_until_user_change",
            ),
            idempotency_key="resolution-enter",
        )
        == entered
    )

    other = ProfileService(context_factory())
    first_source = _source(other, "synthetic-dismiss-a")
    second_source = _source(other, "synthetic-dismiss-b")
    other.submit_observations([_observation(first_source, "2027-05", now)])
    other.submit_observations([_observation(second_source, "2028-05", now + timedelta(minutes=1))])
    other_review = other.list_reviews()[0]
    dismissed = other.resolve_review(
        other_review["id"],
        ResolutionInput(
            action="dismiss",
            alternatives_considered=other_review["candidate_ids"],
            note="Synthetic dismissal",
            scope="until_newer_evidence",
        ),
    )
    assert dismissed["status"] == "dismissed"
    with pytest.raises(ValueError, match="Resolvable"):
        other.resolve_review(
            other_review["id"],
            ResolutionInput(
                action="dismiss",
                scope="until_newer_evidence",
            ),
        )


def test_snapshot_schema_rejection_and_empty_profile(context_factory: Any) -> None:
    service = ProfileService(context_factory())
    assert service.get_current() == []
    assert service.rebuild_projection()["count"] == 0
    assert service.get_dependencies(["missing.field"]) == {"missing.field": []}
    with pytest.raises(ValueError, match="Unsupported ChatGPT"):
        service.import_chatgpt_snapshot({"export_version": "0"})


def test_entered_resolution_yields_to_newer_high_authority_evidence(
    context_factory: Any,
) -> None:
    service = ProfileService(context_factory())
    now = datetime.now(UTC)
    first_source = _source(service, "synthetic-scope-a")
    second_source = _source(service, "synthetic-scope-b")
    service.submit_observations([_observation(first_source, "2027-05", now)])
    service.submit_observations(
        [_observation(second_source, "2028-05", now + timedelta(minutes=1))]
    )
    review = service.list_reviews()[0]
    service.resolve_review(
        review["id"],
        ResolutionInput(
            action="enter",
            entered_value="2029-05",
            alternatives_considered=review["candidate_ids"],
            scope="until_newer_evidence",
        ),
    )
    assert service.get_fact("education.expected_graduation")["value"] == "2029-05"

    official_source = _source(
        service,
        "https://example.org/synthetic-official-transcript",
        source_type=SourceType.OFFICIAL_WEBPAGE,
    )
    service.submit_observations(
        [_observation(official_source, "2030-05", now + timedelta(minutes=2))]
    )
    fact = service.get_fact("education.expected_graduation")
    assert fact["value"] == "2030-05"
    assert fact["verification_status"] == "accepted"


def test_expired_fixed_interval_resolution_does_not_control_projection(
    context_factory: Any,
) -> None:
    service = ProfileService(context_factory())
    now = datetime.now(UTC)
    first_source = _source(service, "synthetic-interval-a")
    second_source = _source(service, "synthetic-interval-b")
    service.submit_observations([_observation(first_source, "2027-05", now)])
    service.submit_observations(
        [_observation(second_source, "2028-05", now + timedelta(minutes=1))]
    )
    review = service.list_reviews()[0]
    resolved = service.resolve_review(
        review["id"],
        ResolutionInput(
            action="enter",
            entered_value="2029-05",
            alternatives_considered=review["candidate_ids"],
            effective_from=now - timedelta(days=2),
            effective_until=now - timedelta(days=1),
            scope="fixed_interval",
        ),
    )
    assert resolved["fact"]["verification_status"] == "conflicted"
    assert service.get_fact("education.expected_graduation")["verification_status"] == "conflicted"
