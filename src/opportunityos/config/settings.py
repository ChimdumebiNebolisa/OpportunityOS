"""Configuration loading and private-path policy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from platformdirs import PlatformDirs
from pydantic import BaseModel, Field


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
    scouts: ScoutBudget = Field(default_factory=ScoutBudget)
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
