"""SQLite schema and transaction module."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from opportunityos.util import new_id, sha256_file, utc_now


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceRow(Base, TimestampMixin):
    __tablename__ = "source_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    official_status: Mapped[str] = mapped_column(String(20), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str | None] = mapped_column(String(200))
    local_artifact_path: Mapped[str | None] = mapped_column(Text)
    trust_class: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ObservationRow(Base, TimestampMixin):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(50), default="profile", nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(36))
    field_path: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    typed_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    value_type: Mapped[str] = mapped_column(String(50), nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False)
    evidence_locator: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extractor_model: Mapped[str | None] = mapped_column(String(200))
    extraction_schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)


class CanonicalFactRow(Base):
    __tablename__ = "canonical_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    field_path: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    typed_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    value_type: Mapped[str] = mapped_column(String(50), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_observation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resolution_id: Mapped[str | None] = mapped_column(String(36))
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewItemRow(Base, TimestampMixin):
    __tablename__ = "review_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    downstream_impact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_id: Mapped[str | None] = mapped_column(String(36))
    deferred_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HumanResolutionRow(Base):
    __tablename__ = "human_resolutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_item_id: Mapped[str] = mapped_column(ForeignKey("review_items.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_candidate_id: Mapped[str | None] = mapped_column(String(36))
    entered_value: Mapped[Any | None] = mapped_column(JSON)
    alternatives_considered: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    resolved_by: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityRow(Base, TimestampMixin):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String(500), nullable=False)
    organization: Mapped[str] = mapped_column(String(500), nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    cycle: Mapped[str | None] = mapped_column(String(50))
    program_family_key: Mapped[str] = mapped_column(String(700), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(800), unique=True, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text, unique=True)
    application_url: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(300))
    delivery_mode: Mapped[str | None] = mapped_column(String(100))
    compensation_or_award: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_timezone: Mapped[str | None] = mapped_column(String(100))
    open_status: Mapped[str] = mapped_column(String(50), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False)
    source_completeness: Mapped[float] = mapped_column(Float, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RequirementRow(Base, TimestampMixin):
    __tablename__ = "opportunity_requirements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    requirement_type: Mapped[str] = mapped_column(String(100), nullable=False)
    field_path: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_predicate: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    hard_or_soft: Mapped[str] = mapped_column(String(10), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False)
    evidence_locator: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(50), nullable=False)


class EligibilityCheckRow(Base):
    __tablename__ = "eligibility_checks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("opportunity_requirements.id"), index=True
    )
    profile_fact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    deterministic_reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    eligibility_ruleset_version: Mapped[str] = mapped_column(String(50), nullable=False)


class AssessmentRow(Base, TimestampMixin):
    __tablename__ = "subjective_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_fact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)


class EvaluationRow(Base, TimestampMixin):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    profile_projection_version: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    eligibility_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_value_score: Mapped[float] = mapped_column(Float, nullable=False)
    effort_penalty: Mapped[float] = mapped_column(Float, nullable=False)
    net_value_score: Mapped[float] = mapped_column(Float, nullable=False)
    decision_label: Mapped[str] = mapped_column(String(30), nullable=False)
    decision_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    strongest_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    main_risk: Mapped[str] = mapped_column(Text, nullable=False)
    total_effort_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    next_action_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    scoring_ruleset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    subjective_assessment_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class ActionItemRow(Base, TimestampMixin):
    __tablename__ = "action_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    readiness_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    completion_ratio: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationRow(Base, TimestampMixin):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), unique=True)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    official_application_url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(100))
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationArtifactRow(Base, TimestampMixin):
    __tablename__ = "application_artifacts"
    __table_args__ = (UniqueConstraint("application_id", "artifact_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    private_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    supporting_fact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    generation_model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    user_approved: Mapped[bool] = mapped_column(default=False, nullable=False)


class DecisionEventRow(Base, TimestampMixin):
    __tablename__ = "decision_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)


class ScoutRunRow(Base):
    __tablename__ = "scout_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    query_plan: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    counters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sources_considered: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    candidates: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    strong_candidates: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    candidate_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    delivered_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_result: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    catch_up_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(100))
    before_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    after_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ruleset_version: Mapped[str | None] = mapped_column(String(50))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyRow(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path.resolve()
        self.engine = create_engine(f"sqlite+pysqlite:///{self.path.as_posix()}", future=True)
        self._configure_sqlite(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _configure_sqlite(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def configure(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        @event.listens_for(engine, "begin")
        def begin_immediate(connection: Any) -> None:
            # Serialize the short local transactions before their first read so
            # check-then-insert idempotency and duplicate guards stay atomic.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def migrate(self, repository_root: Path, backup_root: Path) -> None:
        """Upgrade through Alembic, backing up any existing pre-upgrade schema."""
        configuration_path = repository_root / "alembic.ini"
        migrations_path = repository_root / "migrations"
        if not configuration_path.is_file() or not migrations_path.is_dir():
            raise ValueError("Alembic configuration is missing from the repository root")
        configuration = Config(str(configuration_path))
        configuration.set_main_option("script_location", str(migrations_path))
        configuration.set_main_option(
            "sqlalchemy.url", f"sqlite+pysqlite:///{self.path.as_posix()}"
        )
        configuration.attributes["opportunityos_runtime"] = True
        head = ScriptDirectory.from_config(configuration).get_current_head()
        with self.engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        if current == head:
            return
        existing_tables = set(Base.metadata.tables).intersection(self._table_names())
        if existing_tables:
            self._backup_before_migration(backup_root, current, head)
        command.upgrade(configuration, "head")

    def _table_names(self) -> set[str]:
        with sqlite3.connect(self.path) as connection:
            return {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

    def _backup_before_migration(
        self, backup_root: Path, current_revision: str | None, target_revision: str | None
    ) -> None:
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        destination = backup_root / f"pre-migration-{stamp}-{new_id()}.sqlite3"
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        with sqlite3.connect(destination) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise ValueError("Pre-migration backup integrity check failed")
        manifest = {
            "created_at": utc_now().isoformat(),
            "database": destination.name,
            "sha256": sha256_file(destination),
            "integrity": integrity,
            "from_revision": current_revision,
            "to_revision": target_revision,
        }
        destination.with_suffix(".manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.session_factory() as session, session.begin():
            yield session

    def integrity_check(self) -> str:
        with self.engine.connect() as connection:
            return str(connection.execute(text("PRAGMA integrity_check")).scalar_one())

    def pragma(self, name: str) -> Any:
        if name not in {"foreign_keys", "journal_mode", "busy_timeout", "user_version"}:
            raise ValueError("Unsupported pragma")
        with self.engine.connect() as connection:
            return connection.execute(text(f"PRAGMA {name}")).scalar_one()
