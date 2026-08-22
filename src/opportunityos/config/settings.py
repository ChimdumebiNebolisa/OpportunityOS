"""Configuration loading and private-path policy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from platformdirs import PlatformDirs
from pydantic import BaseModel, Field, model_validator


class ScoringSettings(BaseModel):
    ruleset_version: str = "1.0"
    weights: dict[str, int]
    apply_threshold: int = 75
    maybe_threshold: int = 55
    apply_confidence: float = 0.70


class ScoutBudget(BaseModel):
    max_queries: int = Field(default=8, ge=1, le=100)
    max_candidate_pages: int = Field(default=30, ge=1, le=500)
    max_deep_evaluations: int = Field(default=10, ge=1, le=100)
    max_model_calls: int = Field(default=20, ge=0, le=500)
    max_duration_seconds: int = Field(default=900, ge=30, le=86400)
    max_notifications: int = Field(default=5, ge=0, le=100)
    daily_model_calls: int = Field(default=80, ge=0, le=2000)


class ScoutSettings(ScoutBudget):
    enabled: bool = True
    schedules: dict[str, str] = Field(
        default_factory=lambda: {
            "scholarship": "daily morning",
            "fellowship_research": "monday,wednesday,friday morning",
            "grant_founder": "tuesday,friday morning",
            "competition_technical": "tuesday,saturday morning",
            "general_high_upside": "sunday afternoon",
        }
    )
    catch_up_days: int = Field(default=7, ge=1, le=30)


class DiscoverySettings(BaseModel):
    enabled: bool = True
    schedules: list[str] = Field(default_factory=lambda: ["06:00", "18:00"])
    lenses: list[str] = Field(
        default_factory=lambda: [
            "scholarship",
            "fellowship",
            "undergraduate_research",
            "research_collaboration",
            "grant",
            "founder_program",
            "idea_stage_funding",
            "competition",
            "selective_technical",
            "open_source",
            "ai_ml",
            "ai_safety_security",
            "systems_infrastructure",
            "technical_entrepreneurship",
            "wildcard",
            "profile_gap",
            "similar_to_valued",
        ]
    )
    max_queries: int = Field(default=120, ge=34, le=1000)
    max_candidate_pages: int = Field(default=250, ge=1, le=5000)
    max_deep_evaluations: int = Field(default=40, ge=1, le=500)
    max_model_calls: int = Field(default=120, ge=0, le=2000)
    max_duration_seconds: int = Field(default=2700, ge=60, le=86400)
    max_notifications: int = Field(default=3, ge=0, le=100)
    max_adaptive_depth: int = Field(default=3, ge=0, le=10)
    baseline_min_query_families: int = Field(default=2, ge=1, le=10)
    productive_percent: int = Field(default=70, ge=0, le=100)
    strategic_percent: int = Field(default=15, ge=0, le=100)
    exploratory_percent: int = Field(default=15, ge=1, le=100)
    exploration_floor_percent: int = Field(default=15, ge=1, le=100)
    source_check_budget: int = Field(default=10, ge=0, le=500)
    daily_model_calls: int = Field(default=240, ge=0, le=5000)
    daily_queries: int = Field(default=240, ge=1, le=10000)
    minimum_interval_minutes: int = Field(default=600, ge=0, le=1440)
    catch_up_days: int = Field(default=2, ge=1, le=14)
    saturation_no_novel_queries: int = Field(default=8, ge=1, le=100)
    saturation_no_qualified_queries: int = Field(default=15, ge=1, le=200)
    saturation_duplicate_rate: float = Field(default=0.80, ge=0, le=1)

    @model_validator(mode="after")
    def validate_allocation(self) -> DiscoverySettings:
        if self.productive_percent + self.strategic_percent + self.exploratory_percent != 100:
            raise ValueError("Discovery allocation percentages must total 100")
        if self.exploration_floor_percent > self.exploratory_percent:
            raise ValueError("Exploration floor cannot exceed exploratory allocation")
        if len(self.schedules) != 2:
            raise ValueError("Discovery requires exactly two default schedule times")
        return self


class PersonalSourceSettings(BaseModel):
    enabled: bool = True
    mode: Literal["disabled", "continuous"] = "continuous"
    initial_lookback_days: int = Field(default=365, ge=1, le=3650)
    max_records_per_run: int = Field(default=250, ge=1, le=5000)


class ChatGPTSourceSettings(BaseModel):
    enabled: bool = True
    mode: Literal["disabled", "snapshot_only", "continuous"] = "continuous"
    initial_lookback_days: int = Field(default=365, ge=1, le=3650)
    max_records_per_run: int = Field(default=250, ge=1, le=5000)
    incremental_sync: bool = True
    scope: dict[str, bool] = Field(
        default_factory=lambda: {
            "conversations": True,
            "memory": True,
            "files": False,
        }
    )


class ReconciliationSettings(BaseModel):
    materiality_threshold: float = Field(default=0.65, ge=0, le=1)
    preserve_history: bool = True
    quiet_exact_agreement: bool = True


class ProfileIntelligenceSettings(BaseModel):
    enabled: bool = True
    timezone: str = "America/Chicago"
    schedule: str = "05:00"
    max_duration_seconds: int = Field(default=1800, ge=60, le=86400)
    max_model_calls: int = Field(default=60, ge=0, le=2000)
    review_digest_max_items: int = Field(default=10, ge=1, le=100)
    require_review_for_new_material_facts: bool = True
    github: PersonalSourceSettings = Field(default_factory=PersonalSourceSettings)
    gmail: PersonalSourceSettings = Field(default_factory=PersonalSourceSettings)
    chatgpt: ChatGPTSourceSettings = Field(default_factory=ChatGPTSourceSettings)
    reconciliation: ReconciliationSettings = Field(default_factory=ReconciliationSettings)

    @model_validator(mode="after")
    def validate_schedule(self) -> ProfileIntelligenceSettings:
        parts = self.schedule.split(":")
        if len(parts) != 2 or any(not part.isdigit() for part in parts):
            raise ValueError("Profile intelligence schedule must use HH:MM")
        hour, minute = (int(part) for part in parts)
        if hour > 23 or minute > 59:
            raise ValueError("Profile intelligence schedule must use a valid time")
        return self


class AutoPrepareSettings(BaseModel):
    enabled: bool = True
    score_threshold: float = Field(default=90, ge=0, le=100)
    confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    freshness_hours: int = Field(default=24, ge=1, le=720)
    max_per_day: int = Field(default=2, ge=0, le=100)


class ExecutionSettings(BaseModel):
    high_value_threshold: float = Field(default=80, ge=0, le=100)
    deadline_rescue_hours: int = Field(default=72, ge=1, le=720)
    nudge_min_score: float = Field(default=65, ge=0, le=100)


class NotificationSettings(BaseModel):
    enabled: bool = True
    daily_cap: int = Field(default=3, ge=0, le=100)
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"
    default_snooze_hours: int = Field(default=24, ge=1, le=720)


class BriefSettings(BaseModel):
    daily_enabled: bool = True
    evening_rescue_enabled: bool = True
    weekly_strategy_enabled: bool = True
    max_items: int = Field(default=5, ge=1, le=20)
    minimum_strategy_evidence: int = Field(default=5, ge=1, le=1000)


class FollowUpSettings(BaseModel):
    enabled: bool = True
    default_days: int = Field(default=14, ge=1, le=365)


class BackupSettings(BaseModel):
    auto_enabled: bool = True
    daily_retention: int = Field(default=7, ge=1, le=100)
    weekly_retention: int = Field(default=4, ge=1, le=100)
    monthly_retention: int = Field(default=3, ge=1, le=100)


class HealthSettings(BaseModel):
    enabled: bool = True
    max_scout_silence_hours: int = Field(default=36, ge=1, le=720)
    backup_stale_hours: int = Field(default=168, ge=1, le=2160)


class AutomationSettings(BaseModel):
    enabled: bool = True


class Settings(BaseModel):
    schema_version: str = "1"
    timezone: str = "America/Chicago"
    default_action_minutes: int = Field(default=45, ge=1, le=1440)
    retention_days: int = Field(default=30, ge=1)
    max_attachment_bytes: int = Field(default=33_554_432, ge=1)
    max_pdf_pages: int = Field(default=100, ge=1, le=1000)
    max_web_bytes: int = Field(default=5_242_880, ge=1024)
    web_timeout_seconds: float = Field(default=15, gt=0, le=120)
    scoring: ScoringSettings
    automation: AutomationSettings = Field(default_factory=AutomationSettings)
    scouts: ScoutSettings = Field(default_factory=ScoutSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    profile_intelligence: ProfileIntelligenceSettings = Field(
        default_factory=ProfileIntelligenceSettings
    )
    auto_prepare: AutoPrepareSettings = Field(default_factory=AutoPrepareSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    briefs: BriefSettings = Field(default_factory=BriefSettings)
    followup: FollowUpSettings = Field(default_factory=FollowUpSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    data_dir: Path
    config_dir: Path
    repository_root: Path


def _defaults() -> dict[str, Any]:
    path = Path(__file__).with_name("defaults.yaml")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Public defaults must be a mapping")
    return value


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(
    repository_root: Path | None = None,
    *,
    data_dir: Path | None = None,
    config_dir: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> Settings:
    """Load public defaults, private config, environment paths, and explicit overrides."""
    repo = (repository_root or Path.cwd()).resolve()
    dirs = PlatformDirs("OpportunityOS", "OpportunityOS", roaming=False)
    effective_data = data_dir or Path(os.environ.get("OPPORTUNITYOS_DATA_DIR", dirs.user_data_dir))
    roaming = PlatformDirs("OpportunityOS", "OpportunityOS", roaming=True)
    effective_config = config_dir or Path(
        os.environ.get("OPPORTUNITYOS_CONFIG_DIR", roaming.user_config_dir)
    )
    data_root = effective_data.absolute()
    current = Path(data_root.anchor)
    for part in data_root.parts[1:]:
        current /= part
        is_junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or is_junction():
            raise ValueError("Private data cannot traverse a symlink or junction")
    config_root = effective_config.absolute()
    resolved_config = config_root.resolve(strict=False)
    if resolved_config == repo or resolved_config.is_relative_to(repo):
        raise ValueError("Private configuration directory cannot be inside the repository")
    current = Path(config_root.anchor)
    for part in config_root.parts[1:]:
        current /= part
        is_junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or is_junction():
            raise ValueError("Private configuration cannot traverse a symlink or junction")
    values = _defaults()
    config_file = Path(
        os.environ.get("OPPORTUNITYOS_CONFIG_FILE", effective_config / "config.yaml")
    )
    resolved_file = config_file.resolve(strict=False)
    if not resolved_file.is_relative_to(resolved_config):
        raise ValueError("Private configuration file must be inside the configuration directory")
    current = Path(config_file.absolute().anchor)
    for part in config_file.absolute().parts[1:]:
        current /= part
        is_junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or is_junction():
            raise ValueError("Private configuration cannot traverse a symlink or junction")
    if config_file.is_file():
        private = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        if not isinstance(private, dict):
            raise ValueError("Private configuration must be a mapping")
        values = _merge(values, private)
    if overrides:
        values = _merge(values, overrides)
    values.update(
        data_dir=effective_data.resolve(),
        config_dir=effective_config.resolve(),
        repository_root=repo,
    )
    return Settings.model_validate(values)
