"""Initialization, health, backup, restore, export, purge, and local metrics."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from opportunityos.application.common import audit
from opportunityos.application.context import ApplicationContext
from opportunityos.infrastructure.database import (
    ActionItemRow,
    AuditEventRow,
    Base,
    EvaluationRow,
    ReviewItemRow,
    ScoutRunRow,
)
from opportunityos.security import audit_public_repository
from opportunityos.util import new_id, sha256_file, utc_now


class OperationsService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def initialize(self) -> dict[str, Any]:
        self.context.storage.initialize()
        self.context.database.initialize()
        return {
            "database": str(self.context.database.path),
            "data_root": str(self.context.storage.root),
            "integrity": self.context.database.integrity_check(),
            "private_path_safe": True,
        }

    @staticmethod
    def _command_version(command: str) -> dict[str, Any]:
        executable = shutil.which(command)
        if not executable:
            return {"state": "GATED", "detail": f"{command} is not installed"}
        try:
            completed = subprocess.run(
                [executable, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"state": "FAIL", "detail": f"{command} version check failed"}
        output = (completed.stdout or completed.stderr).strip().splitlines()
        return {
            "state": "PASS" if completed.returncode == 0 else "FAIL",
            "detail": output[0] if output else f"{command} returned {completed.returncode}",
        }

    def status(self) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            latest_backup = max(
                self.context.storage.category_path("backups").glob("*.sqlite3"),
                key=lambda path: path.stat().st_mtime,
                default=None,
            )
            urgent = int(
                session.scalar(
                    select(func.count())
                    .select_from(ReviewItemRow)
                    .where(ReviewItemRow.status == "open", ReviewItemRow.severity == "high")
                )
                or 0
            )
            last_scouts = [
                {
                    "category": row.category,
                    "status": row.status,
                    "ended_at": row.ended_at,
                }
                for row in session.scalars(
                    select(ScoutRunRow).order_by(ScoutRunRow.started_at.desc()).limit(20)
                ).all()
            ]
        findings = audit_public_repository(self.context.settings.repository_root)
        hermes = self._command_version("hermes")
        return {
            "database": {
                "path": str(self.context.database.path),
                "integrity": self.context.database.integrity_check(),
                "foreign_keys": self.context.database.pragma("foreign_keys"),
                "journal_mode": self.context.database.pragma("journal_mode"),
            },
            "private_path_safe": True,
            "latest_backup": str(latest_backup) if latest_backup else None,
            "urgent_review_items": urgent,
            "public_repo_audit": {
                "state": "PASS" if not findings else "FAIL",
                "finding_count": len(findings),
            },
            "hermes": hermes,
            "codex_oauth": {
                "state": "GATED",
                "detail": (
                    "Verify interactively with `hermes model`; credentials are never "
                    "inspected by OpportunityOS."
                ),
            },
            "discord_gateway": {
                "state": "GATED",
                "detail": (
                    "Verify with `hermes gateway status` after configuring the numeric allowlist."
                ),
            },
            "vision": {"state": "GATED", "detail": "Verify in the selected Hermes model."},
            "web_search": {"state": "GATED", "detail": "Verify Hermes DDGS or configured search."},
            "github": {
                "state": "GATED",
                "detail": "Optional authenticated check requires private credentials.",
            },
            "scouts": last_scouts,
            "continuous_operation": False,
        }

    def doctor(self) -> dict[str, Any]:
        status = self.status()
        blocking = []
        if status["database"]["integrity"] != "ok":
            blocking.append("database integrity")
        if status["public_repo_audit"]["state"] != "PASS":
            blocking.append("public repository audit")
        return {
            "result": "PASS" if not blocking else "FAIL",
            "blocking": blocking,
            "checks": status,
        }

    def backup(self) -> dict[str, Any]:
        backup_root = self.context.storage.category_path("backups")
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        destination = self.context.storage.require_private(
            backup_root / f"opportunityos-{stamp}-{new_id()}.sqlite3"
        )
        source_connection = sqlite3.connect(self.context.database.path)
        try:
            destination_connection = sqlite3.connect(destination)
            try:
                source_connection.backup(destination_connection)
            finally:
                destination_connection.close()
        finally:
            source_connection.close()
        integrity_connection = sqlite3.connect(destination)
        try:
            integrity = str(integrity_connection.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            integrity_connection.close()
        if integrity != "ok":
            raise ValueError("Backup integrity check failed")
        manifest = {
            "created_at": utc_now().isoformat(),
            "schema_version": 1,
            "database": destination.name,
            "sha256": sha256_file(destination),
            "integrity": integrity,
        }
        manifest_path = destination.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        with self.context.database.transaction() as session:
            audit(
                session,
                event_type="backup_created",
                reason="manual local backup",
                subject_type="database",
                subject_id=None,
                details={"backup_name": destination.name, "sha256": manifest["sha256"]},
            )
        return {"backup_path": str(destination), "manifest_path": str(manifest_path), **manifest}

    def restore(self, backup_path: Path, target_directory: Path) -> dict[str, Any]:
        backup = self.context.storage.require_private(backup_path)
        if not backup.is_file() or backup.suffix != ".sqlite3":
            raise ValueError("Backup must be a private SQLite backup file")
        manifest_path = backup.with_suffix(".manifest.json")
        if not manifest_path.is_file():
            raise ValueError("Backup manifest is missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("sha256") != sha256_file(backup):
            raise ValueError("Backup hash does not match its manifest")
        connection = sqlite3.connect(backup)
        try:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database integrity check failed")
        finally:
            connection.close()
        target_root = self.context.storage.require_private(target_directory)
        target_root.mkdir(parents=True, exist_ok=True)
        if any(target_root.iterdir()):
            raise ValueError("Restore target must be empty")
        target = self.context.storage.require_private(target_root / "opportunityos.sqlite3")
        with backup.open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        return {"restored_path": str(target), "sha256": sha256_file(target), "source": backup.name}

    def export_json(self) -> Path:
        data: dict[str, list[dict[str, Any]]] = {}
        with self.context.database.engine.connect() as connection:
            for table in Base.metadata.sorted_tables:
                rows = connection.execute(select(table)).mappings().all()
                data[table.name] = [dict(row) for row in rows]
        destination = self.context.storage.require_private(
            self.context.storage.category_path("exports")
            / f"opportunityos-export-{utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        destination.write_text(
            json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        return destination

    def purge_attachments(self, older_than_days: int | None = None) -> int:
        days = self.context.settings.retention_days if older_than_days is None else older_than_days
        if days < 1:
            raise ValueError("Retention days must be positive")
        threshold = datetime.now(UTC) - timedelta(days=days)
        removed = 0
        for path in self.context.storage.category_path("attachments").iterdir():
            if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
                continue
            candidate = self.context.storage.require_private(path)
            if candidate.is_file():
                modified = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
                if modified < threshold:
                    candidate.unlink()
                    removed += 1
        return removed

    def metrics(self) -> dict[str, int]:
        with self.context.database.transaction() as session:
            return {
                "evaluations": int(
                    session.scalar(select(func.count()).select_from(EvaluationRow)) or 0
                ),
                "actions": int(
                    session.scalar(select(func.count()).select_from(ActionItemRow)) or 0
                ),
                "open_reviews": int(
                    session.scalar(
                        select(func.count())
                        .select_from(ReviewItemRow)
                        .where(ReviewItemRow.status == "open")
                    )
                    or 0
                ),
                "scout_runs": int(
                    session.scalar(select(func.count()).select_from(ScoutRunRow)) or 0
                ),
                "audit_events": int(
                    session.scalar(select(func.count()).select_from(AuditEventRow)) or 0
                ),
                "analytics_uploaded": 0,
            }
