"""Validated contracts shared by CLI, MCP, application services, and adapters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class SourceType(StrEnum):
    USER_STATEMENT = "user_statement"
    GITHUB_API = "github_api"
    OFFICIAL_WEBPAGE = "official_webpage"
    UNOFFICIAL_WEBPAGE = "unofficial_webpage"
    LOCAL_DOCUMENT = "local_document"
    CHATGPT_SNAPSHOT = "chatgpt_snapshot"
    EMAIL_IMPORT = "email_import"
    HISTORY = "opportunityos_history"
    MODEL_INFERENCE = "model_inference"


class OfficialStatus(StrEnum):
    OFFICIAL = "official"
    UNOFFICIAL = "unofficial"
    UNKNOWN = "unknown"


class ObservationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    CONFLICTED = "conflicted"


class ReviewType(StrEnum):
    CONFLICT = "conflict"
    STALE = "stale"
    UNVERIFIED = "unverified"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    POSSIBLE_MERGE = "possible_merge"
    SOURCE_FAILURE = "source_failure"
    AUTH_FAILURE = "auth_failure"


class ReviewStatus(StrEnum):
    OPEN = "open"
    DEFERRED = "deferred"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class EligibilityResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"
    NOT_APPLICABLE = "not_applicable"


class OverallEligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REVIEW_REQUIRED = "review_required"


class DecisionLabel(StrEnum):
    APPLY = "apply"
    MAYBE = "maybe"
    PASS = "pass"
    REVIEW_REQUIRED = "review_required"


class LifecycleState(StrEnum):
    DISCOVERED = "discovered"
    SOURCE_VERIFIED = "source_verified"
    PARSED = "parsed"
    ELIGIBILITY_PENDING = "eligibility_pending"
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REVIEW_REQUIRED = "review_required"
    EVALUATED = "evaluated"
    SHORTLISTED = "shortlisted"
    PREPARING = "preparing"
    READY = "ready"
    SUBMITTED = "submitted"
    FOLLOW_UP_DUE = "follow_up_due"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class ActionStatus(StrEnum):
    BLOCKED = "blocked"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"


class PredicateOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    RANGE = "range"
    BEFORE = "before"
    AFTER = "after"
    CONTAINS = "contains"
    ANY_OF = "any_of"
    ALL_OF = "all_of"
    UNKNOWN = "unknown"


class SourceCreate(BaseModel):
    source_type: SourceType
    source_locator: str = Field(min_length=1, max_length=2048)
    display_name: str = Field(min_length=1, max_length=300)
    official_status: OfficialStatus = OfficialStatus.UNKNOWN
    retrieved_at: datetime
    published_at: datetime | None = None
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    mime_type: str | None = Field(default=None, max_length=200)
    local_artifact_path: str | None = None
    trust_class: str = Field(default="unknown", max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationInput(BaseModel):
    field_path: str = Field(min_length=1, max_length=300)
    value: Any
    value_type: str = Field(default="json", max_length=50)
    assertion_kind: Literal["reported", "observed", "inferred"] = "reported"
    source_id: str
    evidence_locator: str = Field(default="", max_length=1000)
    extraction_confidence: float = Field(ge=0, le=1)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    observed_at: datetime
    extractor_model: str | None = Field(default=None, max_length=200)
    extraction_schema_version: str = "1.0"

    @model_validator(mode="after")
    def valid_interval(self) -> ObservationInput:
        if (
            self.effective_from
            and self.effective_until
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("effective_until must be after effective_from")
        return self


class ResolutionInput(BaseModel):
    action: Literal["select", "enter", "contextual", "dismiss"]
    selected_candidate_id: str | None = None
    entered_value: Any | None = None
    alternatives_considered: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    scope: Literal["until_newer_evidence", "fixed_interval", "permanent_until_user_change"]
    resolved_by: str = Field(default="user", max_length=100)

    @model_validator(mode="after")
    def has_choice(self) -> ResolutionInput:
        if self.action == "select" and not self.selected_candidate_id:
            raise ValueError("select requires selected_candidate_id")
        if self.action == "enter" and self.entered_value is None:
            raise ValueError("enter requires entered_value")
        if (
            self.effective_from
            and self.effective_until
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("effective_until must be after effective_from")
        if self.scope == "fixed_interval" and not (self.effective_from and self.effective_until):
            raise ValueError("fixed_interval requires effective_from and effective_until")
        return self


class OpportunityInput(BaseModel):
    canonical_title: str = Field(min_length=1, max_length=500)
    organization: str = Field(min_length=1, max_length=500)
    opportunity_type: str = Field(min_length=1, max_length=100)
    cycle: str | None = Field(default=None, max_length=50)
    canonical_url: HttpUrl | None = None
    application_url: HttpUrl | None = None
    location: str | None = Field(default=None, max_length=300)
    delivery_mode: str | None = Field(default=None, max_length=100)
    compensation_or_award: dict[str, Any] = Field(default_factory=dict)
    deadline_at: datetime | None = None
    deadline_timezone: str | None = Field(default=None, max_length=100)
    open_status: str = Field(default="unknown", max_length=50)
    source_completeness: float = Field(default=0, ge=0, le=1)
    source_ids: list[str] = Field(min_length=1)


class RequirementInput(BaseModel):
    opportunity_id: str
    requirement_type: str = Field(min_length=1, max_length=100)
    field_path: str = Field(min_length=1, max_length=300)
    operator: PredicateOperator
    expected: Any = None
    hard: bool = True
    extracted_text: str = Field(min_length=1, max_length=5000)
    source_id: str
    evidence_locator: str = Field(default="", max_length=1000)
    extraction_confidence: float = Field(ge=0, le=1)
    status: Literal["verified", "ambiguous", "missing", "superseded"] = "verified"
    ruleset_version: str = "1.0"


class AssessmentInput(BaseModel):
    opportunity_id: str
    dimension: str = Field(min_length=1, max_length=100)
    value: float = Field(ge=0, le=10)
    rationale: str = Field(min_length=1, max_length=3000)
    supporting_fact_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)
    model_provider: str = Field(max_length=100)
    model_id: str = Field(max_length=200)
    prompt_version: str = Field(max_length=100)


class ActionInput(BaseModel):
    opportunity_id: str | None = None
    action_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    estimated_minutes: int = Field(ge=1, le=100_000)
    due_at: datetime | None = None
    dependencies: list[str] = Field(default_factory=list)
    readiness_score: float = Field(ge=0, le=100)
    status: ActionStatus = ActionStatus.READY


class ClaimInput(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    supporting_fact_ids: list[str]
    status: Literal["verified", "user_approved", "needs_review"] = "verified"


class ScoutRunInput(BaseModel):
    category: Literal[
        "scholarship",
        "fellowship_research",
        "grant_founder",
        "competition_technical",
        "general_high_upside",
    ]
    query_plan: list[str] = Field(default_factory=list, max_length=100)
    budget: dict[str, int]


class ResultEnvelope(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None
