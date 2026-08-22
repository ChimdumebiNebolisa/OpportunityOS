"""Private backup automation and actionable local health state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from opportunityos.application.common import audit
from opportunityos.application.context import ApplicationContext
from opportunityos.application.operations import OperationsService
from opportunityos.infrastructure.database import DiscoveryRunRow, HealthStateRow, ScoutRunRow
from opportunityos.util import sha256_file, utc_now


class HealthService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def _record(
        self,
        session: Any,
        component: str,
        *,
        status: str,
        detail_code: str,
        success: bool,
        fingerprint: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        row = session.get(HealthStateRow, component)
        if row is None:
            row = HealthStateRow(
                component=component,
                status=status,
                checked_at=now,
                last_success_at=now if success else None,
                consecutive_failures=0 if success else 1,
                detail_code=detail_code,
                notification_fingerprint=fingerprint,
            )
            session.add(row)
        else:
            row.status = status
            row.checked_at = now
            row.last_success_at = now if success else row.last_success_at
            row.consecutive_failures = 0 if success else row.consecutive_failures + 1
            row.detail_code = detail_code
            if fingerprint:
                row.notification_fingerprint = fingerprint
        return {
            "component": component,
            "status": status,
            "detail_code": detail_code,
            "consecutive_failures": row.consecutive_failures,
            "last_success_at": row.last_success_at,
        }

    def check(self) -> dict[str, Any]:
        if not self.context.settings.health.enabled:
            return {"status": "disabled", "components": []}
        now = utc_now()
        components: list[dict[str, Any]] = []
        with self.context.database.transaction() as session:
            integrity = self.context.database.integrity_check()
            components.append(
                self._record(
                    session,
                    "database",
                    status="healthy" if integrity == "ok" else "unhealthy",
                    detail_code="ok" if integrity == "ok" else "integrity_failed",
                    success=integrity == "ok",
                )
            )
            if self.context.settings.discovery.enabled:
                latest_discovery = session.scalar(
                    select(DiscoveryRunRow)
                    .where(DiscoveryRunRow.status.in_(["success", "partial", "budget_stopped"]))
                    .order_by(DiscoveryRunRow.ended_at.desc())
                )
                discovery_recent = bool(
                    latest_discovery
                    and latest_discovery.ended_at
                    and now
                    - (
                        latest_discovery.ended_at
                        if latest_discovery.ended_at.tzinfo
                        else latest_discovery.ended_at.replace(tzinfo=UTC)
                    )
                    <= timedelta(hours=self.context.settings.health.max_scout_silence_hours)
                )
                discovery_healthy = bool(
                    discovery_recent
                    and latest_discovery
                    and latest_discovery.status == "success"
                    and latest_discovery.deep_contract_satisfied
                )
                components.append(
                    self._record(
                        session,
                        "discovery",
                        status="healthy" if discovery_healthy else "unhealthy",
                        detail_code=(
                            "recent_complete" if discovery_healthy else "stale_or_incomplete"
                        ),
                        success=discovery_healthy,
                    )
                )
            latest_scout = session.scalar(
                select(ScoutRunRow)
                .where(ScoutRunRow.status.in_(["success", "partial"]))
                .order_by(ScoutRunRow.ended_at.desc())
            )
            scout_ok = bool(
                latest_scout
                and latest_scout.ended_at
                and now
                - (
                    latest_scout.ended_at
                    if latest_scout.ended_at.tzinfo
                    else latest_scout.ended_at.replace(tzinfo=UTC)
                )
                <= timedelta(hours=self.context.settings.health.max_scout_silence_hours)
            )
            components.append(
                self._record(
                    session,
                    "scouts",
                    status="healthy" if scout_ok else "unhealthy",
                    detail_code="recent_success" if scout_ok else "stale_success",
                    success=scout_ok,
                )
            )
            discovery_schedules_ok = len(self.context.settings.discovery.schedules) == 2 and all(
                str(item).strip() for item in self.context.settings.discovery.schedules
            )
            components.append(
                self._record(
                    session,
                    "discovery_schedules",
                    status="healthy" if discovery_schedules_ok else "unhealthy",
                    detail_code=(
                        "configured" if discovery_schedules_ok else "missing_configuration"
                    ),
                    success=discovery_schedules_ok,
                )
            )
            expected_categories = {
                "scholarship",
                "fellowship_research",
                "grant_founder",
                "competition_technical",
                "general_high_upside",
            }
            configured_schedules = self.context.settings.scouts.schedules
            schedules_ok = expected_categories <= set(configured_schedules) and all(
                str(configured_schedules[key]).strip() for key in expected_categories
            )
            components.append(
                self._record(
                    session,
                    "schedules",
                    status="healthy" if schedules_ok else "unhealthy",
                    detail_code="configured" if schedules_ok else "missing_configuration",
                    success=schedules_ok,
                )
            )
            latest_backup = self._latest_backup()
            backup_ok = bool(
                latest_backup
                and now - datetime.fromtimestamp(latest_backup.stat().st_mtime, UTC)
                <= timedelta(hours=self.context.settings.health.backup_stale_hours)
            )
            components.append(
                self._record(
                    session,
                    "backups",
                    status="healthy" if backup_ok else "unhealthy",
                    detail_code="fresh" if backup_ok else "stale_or_missing",
                    success=backup_ok,
                )
            )
            unhealthy = [item for item in components if item["status"] != "healthy"]
            return {
                "status": "healthy" if not unhealthy else "unhealthy",
                "components": components,
                "actionable_failures": [item["detail_code"] for item in unhealthy],
            }

    def record_live_test(self, component: str, success: bool, detail_code: str) -> dict[str, Any]:
        if not component or len(component) > 100:
            raise ValueError("component must be a short non-empty name")
        with self.context.database.transaction() as session:
            result = self._record(
                session,
                component,
                status="healthy" if success else "unhealthy",
                detail_code=detail_code[:100],
                success=success,
            )
            audit(
                session,
                event_type="health_live_test_recorded",
                reason="explicit local/live health evidence recorded",
                subject_type="health",
                subject_id=component,
                details={"success": success, "detail_code": detail_code[:100]},
            )
            return result

    def _latest_backup(self) -> Path | None:
        return max(
            self.context.storage.category_path("backups").glob("*.sqlite3"),
            key=lambda path: path.stat().st_mtime,
            default=None,
        )

    def backup_status(self) -> dict[str, Any]:
        latest = self._latest_backup()
        if latest is None:
            return {"latest": None, "fresh": False}
        return {
            "latest": str(latest),
            "fresh": datetime.now(UTC) - datetime.fromtimestamp(latest.stat().st_mtime, UTC)
            <= timedelta(hours=self.context.settings.health.backup_stale_hours),
            "sha256": sha256_file(latest),
        }

    def backup_auto(self) -> dict[str, Any]:
        if not self.context.settings.backup.auto_enabled:
            return {"status": "disabled"}
        latest = self._latest_backup()
        database_mtime = self.context.database.path.stat().st_mtime
        due = latest is None or database_mtime > latest.stat().st_mtime
        if latest is not None:
            due = due or datetime.now(UTC) - datetime.fromtimestamp(
                latest.stat().st_mtime, UTC
            ) >= timedelta(days=7)
        if not due:
            return {"status": "skipped", "reason": "backup is current", **self.backup_status()}
        result = OperationsService(self.context).backup()
        self._retain()
        return {"status": "created", **result}

    def _retain(self) -> None:
        """Apply bounded retention to backup artifacts within the private root only."""
        root = self.context.storage.category_path("backups")
        files = sorted(root.glob("*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
        maximum = (
            self.context.settings.backup.daily_retention
            + self.context.settings.backup.weekly_retention
            + self.context.settings.backup.monthly_retention
        )
        for path in files[maximum:]:
            manifest = path.with_suffix(".manifest.json")
            path.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)
