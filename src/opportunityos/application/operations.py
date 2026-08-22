"""Initialization, health, backup, restore, export, purge, and local metrics."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from opportunityos.application.common import audit
from opportunityos.application.context import ApplicationContext
from opportunityos.infrastructure.database import (
    ActionItemRow,
    AuditEventRow,
    AutomationControlRow,
    Base,
    DiscoveryRunRow,
    EvaluationRow,
    HealthStateRow,
    PersonalSourceSyncStateRow,
    ProfileIntelligenceRunRow,
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
    def _hermes_executable() -> str | None:
        """Resolve the supported Hermes launcher without relying on a refreshed shell PATH."""
        executable = shutil.which("hermes")
        if executable:
            return executable

        candidates: list[Path] = []
        hermes_home = os.environ.get("HERMES_HOME")
        if hermes_home:
            home = Path(hermes_home).expanduser()
            candidates.extend(
                [
                    home / "hermes-agent" / "bin" / "hermes.exe",
                    home / "hermes-agent" / "venv" / "bin" / "hermes",
                    home / "hermes-agent" / "bin" / "hermes",
                ]
            )
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(
                Path(local_app_data) / "hermes" / "hermes-agent" / "bin" / "hermes.exe"
            )
        candidates.append(Path.home() / ".local" / "bin" / "hermes")
        return next((str(path) for path in candidates if path.is_file()), None)

    @staticmethod
    def _run_hermes(
        executable: str, arguments: list[str]
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                [executable, *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _process_running(process_id: int) -> bool:
        if process_id < 1:
            return False
        if os.name == "nt":
            import ctypes

            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return False
            handle = windll.kernel32.OpenProcess(0x1000, False, process_id)
            if not handle:
                return False
            windll.kernel32.CloseHandle(handle)
            return True
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @classmethod
    def _hermes_gateway_running(cls) -> bool:
        homes: list[Path] = []
        if hermes_home := os.environ.get("HERMES_HOME"):
            homes.append(Path(hermes_home).expanduser())
        if local_app_data := os.environ.get("LOCALAPPDATA"):
            homes.append(Path(local_app_data) / "hermes")
        homes.append(Path.home() / ".hermes")
        for home in homes:
            pid_file = home / "gateway.pid"
            if not pid_file.is_file():
                continue
            try:
                raw = pid_file.read_text(encoding="utf-8").strip()
                payload = json.loads(raw)
                process_id = int(payload["pid"] if isinstance(payload, dict) else raw)
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                continue
            if cls._process_running(process_id):
                return True
        return False

    @classmethod
    def _command_version(cls, command: str) -> dict[str, Any]:
        executable = cls._hermes_executable() if command == "hermes" else shutil.which(command)
        if not executable:
            return {"state": "GATED", "detail": f"{command} is not installed"}
        completed = cls._run_hermes(executable, ["--version"])
        if completed is None:
            return {"state": "FAIL", "detail": f"{command} version check failed"}
        output = (completed.stdout or completed.stderr).strip().splitlines()
        return {
            "state": "PASS" if completed.returncode == 0 else "FAIL",
            "detail": output[0] if output else f"{command} returned {completed.returncode}",
        }

    @classmethod
    def _hermes_integrations(cls, executable: str | None) -> dict[str, dict[str, str]]:
        unavailable = {
            "state": "GATED",
            "detail": "Hermes is unavailable, so this state could not be checked.",
        }
        if executable is None:
            return {
                "codex_oauth": dict(unavailable),
                "opportunityos_mcp": dict(unavailable),
                "discord_configuration": dict(unavailable),
                "discord_gateway": dict(unavailable),
                "live_verification": dict(unavailable),
            }

        gateway_running = cls._hermes_gateway_running()
        # Hermes startup can take several seconds on Windows. These independent,
        # read-only probes run together so status latency is bounded by one startup.
        with ThreadPoolExecutor(max_workers=3) as executor:
            auth_future = executor.submit(
                cls._run_hermes, executable, ["auth", "status", "openai-codex"]
            )
            mcp_future = executor.submit(cls._run_hermes, executable, ["mcp", "list"])
            gateway_future = (
                None
                if gateway_running
                else executor.submit(cls._run_hermes, executable, ["gateway", "list"])
            )
            auth = auth_future.result()
            mcp = mcp_future.result()
            gateway = None if gateway_future is None else gateway_future.result()
        auth_output = "" if auth is None else f"{auth.stdout}\n{auth.stderr}".lower()
        codex_oauth = (
            {"state": "PASS", "detail": "Hermes reports OpenAI Codex OAuth logged in."}
            if auth is not None and auth.returncode == 0 and "logged in" in auth_output
            else {
                "state": "GATED",
                "detail": "Run `hermes auth status openai-codex`; credentials are not inspected.",
            }
        )

        mcp_output = "" if mcp is None else f"{mcp.stdout}\n{mcp.stderr}".lower()
        opportunityos_enabled = any(
            re.search(r"\bopportunityos\b", line) and re.search(r"\benabled\b", line)
            for line in mcp_output.splitlines()
        )
        opportunityos_mcp = (
            {"state": "PASS", "detail": "Hermes reports the OpportunityOS MCP server enabled."}
            if mcp is not None and mcp.returncode == 0 and opportunityos_enabled
            else {
                "state": "GATED",
                "detail": "Verify configuration with `hermes mcp list`.",
            }
        )

        gateway_output = "" if gateway is None else f"{gateway.stdout}\n{gateway.stderr}"
        gateway_running = gateway_running or bool(
            gateway is not None
            and gateway.returncode == 0
            and re.search(r"\bPID\s+\d+\b", gateway_output)
        )
        discord_gateway = (
            {
                "state": "PASS",
                "detail": (
                    "A Hermes gateway process is running; this does not prove Discord routing."
                ),
            }
            if gateway_running
            else {
                "state": "GATED",
                "detail": "No running Hermes gateway was reported by `hermes gateway list`.",
            }
        )
        return {
            "codex_oauth": codex_oauth,
            "opportunityos_mcp": opportunityos_mcp,
            "discord_configuration": {
                "state": "GATED",
                "detail": (
                    "Private Discord token and allowlist configuration is not inspected; "
                    "verify it in Hermes."
                ),
            },
            "discord_gateway": discord_gateway,
            "live_verification": {
                "state": "GATED",
                "detail": (
                    "Status performs no external message; record a controlled Hermes/Discord "
                    "round trip separately."
                ),
            },
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
            last_discovery = [
                {
                    "run_id": row.id,
                    "status": row.status,
                    "deep_contract_satisfied": row.deep_contract_satisfied,
                    "delivery_result": row.delivery_result,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                }
                for row in session.scalars(
                    select(DiscoveryRunRow).order_by(DiscoveryRunRow.started_at.desc()).limit(5)
                ).all()
            ]
            last_profile_intelligence = [
                {
                    "run_id": row.id,
                    "status": row.status,
                    "delivery_result": row.delivery_result,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                    "completed_sources": row.completed_sources,
                    "blocked_sources": row.blocked_sources,
                    "counters": row.counters,
                }
                for row in session.scalars(
                    select(ProfileIntelligenceRunRow)
                    .order_by(ProfileIntelligenceRunRow.started_at.desc())
                    .limit(5)
                ).all()
            ]
            profile_sources = [
                {
                    "source_type": row.source_type,
                    "configured_mode": row.configured_mode,
                    "status": row.status,
                    "detail_code": row.detail_code,
                    "cursor": row.cursor,
                    "last_success_at": row.last_success_at,
                    "consecutive_failures": row.consecutive_failures,
                }
                for row in session.scalars(select(PersonalSourceSyncStateRow)).all()
            ]
            health_state = [
                {
                    "component": row.component,
                    "status": row.status,
                    "detail_code": row.detail_code,
                    "checked_at": row.checked_at,
                    "last_success_at": row.last_success_at,
                    "consecutive_failures": row.consecutive_failures,
                }
                for row in session.scalars(select(HealthStateRow)).all()
            ]
            automation_controls = [
                {
                    "key": row.key,
                    "enabled": row.enabled,
                    "reason": row.reason,
                    "updated_at": row.updated_at,
                }
                for row in session.scalars(select(AutomationControlRow)).all()
            ]
        findings = audit_public_repository(self.context.settings.repository_root)
        hermes_executable = self._hermes_executable()
        hermes = self._command_version("hermes")
        integrations = self._hermes_integrations(hermes_executable)
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
            **integrations,
            "vision": {"state": "GATED", "detail": "Verify in the selected Hermes model."},
            "web_search": {"state": "GATED", "detail": "Verify Hermes DDGS or configured search."},
            "github": {
                "state": "GATED",
                "detail": "Optional authenticated check requires private credentials.",
            },
            "scouts": last_scouts,
            "discovery": {
                "enabled": self.context.settings.discovery.enabled,
                "schedules": self.context.settings.discovery.schedules,
                "runs": last_discovery,
            },
            "personal_intelligence": {
                "enabled": self.context.settings.profile_intelligence.enabled,
                "schedule": self.context.settings.profile_intelligence.schedule,
                "timezone": self.context.settings.profile_intelligence.timezone,
                "runs": last_profile_intelligence,
                "sources": profile_sources,
            },
            "health": health_state,
            "automation_controls": automation_controls,
            "continuous_operation": integrations["discord_gateway"]["state"] == "PASS",
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
