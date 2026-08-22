"""Read-only personal-source adapter seams for V3.1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from opportunityos.adapters.github import GitHubAuthRequiredError, GitHubClient
from opportunityos.domain.personal_intelligence import content_fingerprint


class PersonalSourceError(ValueError):
    """Base error for a bounded personal-source read."""


class PersonalSourceUnavailableError(PersonalSourceError):
    """The configured source cannot be read by the current authorized runtime."""


@dataclass(frozen=True)
class AdapterCapability:
    source_type: str
    available: bool
    operations: tuple[str, ...]
    authorization_status: str
    detail_code: str


@dataclass(frozen=True)
class PersonalCandidate:
    field_path: str
    value: Any
    evidence_locator: str
    extraction_confidence: float = 0.8
    assertion_kind: str = "observed"
    source_event_at: datetime | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    subject_identity: str = "user"
    extractor_model: str | None = None


@dataclass(frozen=True)
class PersonalSourceRecord:
    locator: str
    display_name: str
    content_fingerprint: str
    observed_at: datetime
    source_event_at: datetime | None = None
    subject_identity: str = "user"
    evidence_excerpt: str = ""
    metadata: dict[str, Any] | None = None
    observations: tuple[PersonalCandidate, ...] = ()


@dataclass(frozen=True)
class PersonalSourceBatch:
    records: tuple[PersonalSourceRecord, ...]
    cursor_after: str | None
    high_water_mark: datetime | None
    records_inspected: int
    model_calls: int = 0


class PersonalSourceAdapter(Protocol):
    source_type: str

    def capability(self) -> AdapterCapability: ...

    def fetch(self, *, cursor: str | None, limit: int) -> PersonalSourceBatch: ...


class UnavailablePersonalAdapter:
    def __init__(self, source_type: str, detail_code: str) -> None:
        self.source_type = source_type
        self.detail_code = detail_code

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            source_type=self.source_type,
            available=False,
            operations=(),
            authorization_status="unavailable",
            detail_code=self.detail_code,
        )

    def fetch(self, *, cursor: str | None, limit: int) -> PersonalSourceBatch:
        raise PersonalSourceUnavailableError(self.detail_code)


class GitHubPersonalAdapter:
    """Wrap the existing objective GitHub adapter without adding write methods."""

    source_type = "github"

    def __init__(self, username: str, client: GitHubClient | None = None) -> None:
        if not username.strip():
            raise ValueError("GitHub username is required for personal intelligence")
        self.username = username.strip()
        self.client = client or GitHubClient()

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            source_type=self.source_type,
            available=True,
            operations=("repository_metadata", "releases", "merged_pull_requests"),
            authorization_status="configured",
            detail_code="objective_metadata_available",
        )

    @staticmethod
    def _event_time(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def fetch(self, *, cursor: str | None, limit: int) -> PersonalSourceBatch:
        try:
            evidence = self.client.repository_evidence(self.username)
        except GitHubAuthRequiredError as error:
            raise PersonalSourceUnavailableError("github_auth_required") from error
        if len(evidence) > limit * 20:
            evidence = evidence[: limit * 20]
        payload = [
            {"field_path": item.field_path, "value": item.value, "url": item.evidence_url}
            for item in evidence
        ]
        fingerprint = content_fingerprint(
            locator=f"github:{self.username}",
            content=json.dumps(payload, sort_keys=True),
        )
        if cursor and cursor == fingerprint:
            return PersonalSourceBatch((), cursor, None, 0)
        candidates = tuple(
            PersonalCandidate(
                field_path=item.field_path,
                value=item.value,
                evidence_locator=item.evidence_url,
                extraction_confidence=0.95,
                assertion_kind="observed",
                source_event_at=self._event_time(item.value),
            )
            for item in evidence
        )
        event_times = [item.source_event_at for item in candidates if item.source_event_at]
        return PersonalSourceBatch(
            records=(
                PersonalSourceRecord(
                    locator=f"github:{self.username}",
                    display_name=f"GitHub metadata for {self.username}",
                    content_fingerprint=fingerprint,
                    observed_at=datetime.now().astimezone(),
                    source_event_at=max(event_times) if event_times else None,
                    evidence_excerpt="Objective GitHub metadata; no subjective expertise claim.",
                    metadata={"username": self.username, "evidence_count": len(evidence)},
                    observations=candidates,
                ),
            ),
            cursor_after=fingerprint,
            high_water_mark=max(event_times) if event_times else None,
            records_inspected=1,
        )


class GmailPersonalAdapter(UnavailablePersonalAdapter):
    """Capability-gated read-only seam for a future authorized Gmail provider."""

    def __init__(self) -> None:
        super().__init__("gmail", "gmail_provider_unavailable")


class ChatGPTPersonalAdapter(UnavailablePersonalAdapter):
    """Continuous ChatGPT access is unavailable unless an authorized provider is supplied."""

    def __init__(self) -> None:
        super().__init__("chatgpt", "chatgpt_continuous_capability_unavailable")
