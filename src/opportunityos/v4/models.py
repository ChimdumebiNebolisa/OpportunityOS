"""Versioned contracts exchanged between an agent and OpportunityOS."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1


class Candidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = 1
    title: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source_url: str
    official_url: str | None = None
    application_url: str | None = None
    status: str = "open"
    first_party: bool | None = None
    published_at: str | None = None
    verified_at: str | None = None
    deadline: str | None = None
    location: Any = None
    eligibility: dict[str, Any] = Field(default_factory=dict)
    funding: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_url", "official_url", "application_url")
    @classmethod
    def validate_url_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("URLs must use HTTP or HTTPS")
        return value


FeedbackType = Literal[
    "useful",
    "not_useful",
    "already_known",
    "duplicate",
    "stale",
    "closed",
    "ineligible",
    "wrong_category",
    "bad_source",
    "good_source",
    "false_positive",
    "missed_opportunity",
    "custom",
]


class FeedbackInput(BaseModel):
    schema_version: int = 1
    opportunity_id: str | None = None
    run_id: str | None = None
    type: FeedbackType
    reason: str = ""
    text: str = ""


class StrategyProposal(BaseModel):
    schema_version: int = 1
    reason: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    scope: str = Field(min_length=1)
    changes: dict[str, Any]
    proposed_by: str = Field(min_length=1)
    model: str | None = None
    created_at: str | None = None
