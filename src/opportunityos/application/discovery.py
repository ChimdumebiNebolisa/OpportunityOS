"""Stateful V3 discovery planning, coverage, and search-performance interface."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any, cast

from sqlalchemy import func, select

from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.domain.discovery import (
    DISCOVERY_LENSES,
    DISCOVERY_RULESET_VERSION,
    allocate_queries,
    canonical_source_domain,
    coverage_contract,
    deterministic_yield,
    lens_class,
    normalize_query,
    query_family,
    recent_yield,
    saturation_decision,
)
from opportunityos.infrastructure.database import (
    AutomationControlRow,
    CanonicalFactRow,
    DiscoveryRunRow,
    OpportunityRow,
    QueryStrategyRow,
    ScoutRunRow,
    SearchBranchRow,
    SourceRegistryRow,
    SourceRow,
)
from opportunityos.schemas import (
    DiscoveryExpansionInput,
    DiscoveryQueryInput,
    DiscoverySourceCheckInput,
)
from opportunityos.util import new_id, utc_now

COUNTER_KEYS = (
    "queries",
    "pages",
    "model_calls",
    "raw",
    "novel",
    "qualified",
    "duplicate",
    "official_verified",
    "deep_evaluated",
    "eligible",
    "apply",
    "maybe",
    "passed",
    "stale",
    "closed",
    "failures",
    "source_checks",
    "adaptive_branches",
    "saturation_stops",
    "hard_budget_stops",
    "budget_reallocations",
    "reallocated_queries",
    "material_deliveries",
)

BASELINE_TEMPLATES: dict[str, tuple[str, str]] = {
    "scholarship": (
        "scholarship funding student application",
        "site:official scholarship program application funding",
    ),
    "fellowship": (
        "student fellowship program application",
        "funded fellowship emerging technical talent",
    ),
    "undergraduate_research": (
        "undergraduate research program computer science",
        "funded undergraduate research application",
    ),
    "research_collaboration": (
        "research assistant collaboration student opportunity",
        "research lab student collaboration application",
    ),
    "grant": (
        "student grant technical project application",
        "small grant early technical project funding",
    ),
    "founder_program": (
        "pre-founder founder program early stage",
        "student founder accelerator application",
    ),
    "idea_stage_funding": (
        "idea stage funding technical project",
        "early idea grant prototype funding",
    ),
    "competition": (
        "selective technical competition student",
        "software engineering competition application",
    ),
    "selective_technical": (
        "selective technical program student application",
        "advanced software systems program student",
    ),
    "open_source": (
        "open source mentorship program contributor",
        "selective maintainer contributor opportunity",
    ),
    "ai_ml": (
        "AI machine learning student program",
        "machine learning research opportunity student",
    ),
    "ai_safety_security": (
        "AI safety security student program",
        "AI security research fellowship application",
    ),
    "systems_infrastructure": (
        "systems software infrastructure student program",
        "distributed systems open source opportunity",
    ),
    "technical_entrepreneurship": (
        "technical entrepreneurship student program",
        "software founder technical venture opportunity",
    ),
    "wildcard": (
        "high upside student technical opportunity",
        "emerging unusual funded opportunity technical talent",
    ),
    "profile_gap": (
        "opportunity to build missing research signal",
        "funded opportunity to strengthen technical portfolio",
    ),
    "similar_to_valued": (
        "program similar to valued selective opportunity",
        "related funded opportunity same technical archetype",
    ),
}


def _empty_metrics() -> dict[str, int]:
    return {key: 0 for key in COUNTER_KEYS}


def _add_metrics(current: dict[str, Any], increments: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = dict(current)
    for key in COUNTER_KEYS:
        result[key] = int(current.get(key, 0))
    for key, value in increments.items():
        if key in result:
            result[key] += int(value)
    return result


class DiscoveryService:
    """Deep module owning V3 discovery state while Hermes owns search execution."""

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def _enabled_lenses(self) -> list[str]:
        configured = list(dict.fromkeys(self.context.settings.discovery.lenses))
        unknown = sorted(set(configured) - set(DISCOVERY_LENSES))
        if unknown or not configured:
            raise ValueError(f"Unsupported or empty discovery lens configuration: {unknown}")
        return configured

    @staticmethod
    def _safe_reason(value: str) -> str:
        return " ".join(value.strip().split())[:500]

    def _automation_enabled(self, session: Any) -> bool:
        if (
            not self.context.settings.automation.enabled
            or not self.context.settings.discovery.enabled
        ):
            return False
        row = session.get(AutomationControlRow, "automation")
        discovery = session.get(AutomationControlRow, "discovery")
        return not ((row and not row.enabled) or (discovery and not discovery.enabled))

    @staticmethod
    def _profile_projection(session: Any) -> int:
        projection = session.scalar(
            select(CanonicalFactRow.projection_version)
            .order_by(CanonicalFactRow.projection_version.desc())
            .limit(1)
        )
        return int(projection or 0)

    def _branch_budget(self, allocated_queries: int) -> dict[str, int]:
        settings = self.context.settings.discovery
        return {
            "max_queries": allocated_queries,
            "max_candidate_pages": max(1, settings.max_candidate_pages),
            "max_deep_evaluations": settings.max_deep_evaluations,
            "max_model_calls": settings.max_model_calls,
            "max_duration_seconds": settings.max_duration_seconds,
            "max_notifications": settings.max_notifications,
            "daily_model_calls": settings.daily_model_calls,
        }

    def _strategy(
        self,
        session: Any,
        *,
        lens: str,
        template: str,
        profile_projection_version: int,
        parent_strategy_id: str | None = None,
        seed_opportunity_id: str | None = None,
        seed_source_id: str | None = None,
        generation_reason: str = "configured baseline strategy",
    ) -> QueryStrategyRow:
        normalized = normalize_query(template)
        family = query_family(normalized)
        row = session.scalar(
            select(QueryStrategyRow).where(
                QueryStrategyRow.lens == lens,
                QueryStrategyRow.query_family == family,
                QueryStrategyRow.query_template == normalized,
            )
        )
        if row is not None:
            return cast(QueryStrategyRow, row)
        now = utc_now()
        row = QueryStrategyRow(
            id=new_id(),
            lens=lens,
            query_family=family,
            query_template=normalized,
            parent_strategy_id=parent_strategy_id,
            seed_opportunity_id=seed_opportunity_id,
            seed_source_id=seed_source_id,
            generation_reason=self._safe_reason(generation_reason),
            profile_projection_version=profile_projection_version,
            first_used_at=None,
            last_used_at=None,
            use_count=0,
            metrics={},
            historical_yield=0,
            recent_yield=0,
            disabled=False,
            disabled_reason=None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return row

    def _scout_row(
        self,
        *,
        run_id: str,
        branch_id: str,
        lens: str,
        allocated_queries: int,
        started_at: datetime,
    ) -> ScoutRunRow:
        return ScoutRunRow(
            id=new_id(),
            category=lens,
            query_plan=[],
            budget=self._branch_budget(allocated_queries),
            counters={
                "queries": 0,
                "pages": 0,
                "model_calls": 0,
                "deep_evaluations": 0,
                "notifications": 0,
                "budget_stops": 0,
            },
            sources_considered=[],
            candidates=[],
            strong_candidates=[],
            candidate_versions={},
            delivered_versions={},
            errors=[],
            started_at=started_at,
            ended_at=None,
            delivery_result=None,
            status="running",
            catch_up_from=None,
            discovery_run_id=run_id,
            branch_id=branch_id,
        )

    def begin_global(self, *, idempotency_key: str | None = None) -> dict[str, Any]:
        operation = "discovery.begin_global"
        settings = self.context.settings.discovery
        lenses = self._enabled_lenses()
        allocations = allocate_queries(
            total=settings.max_queries,
            lenses=lenses,
            baseline=settings.baseline_min_query_families,
            productive_percent=settings.productive_percent,
            strategic_percent=settings.strategic_percent,
            exploratory_percent=settings.exploratory_percent,
        )
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            if not self._automation_enabled(session):
                raise ValueError("Global discovery automation is disabled")
            active = session.scalar(
                select(DiscoveryRunRow).where(DiscoveryRunRow.status == "running")
            )
            if active is not None:
                raise ValueError("A global discovery run is already active")
            now = utc_now()
            previous_run = session.scalar(
                select(DiscoveryRunRow)
                .where(DiscoveryRunRow.status.in_(["success", "partial", "budget_stopped"]))
                .order_by(DiscoveryRunRow.ended_at.desc())
            )
            catch_up_from: datetime | None = None
            if previous_run and previous_run.ended_at:
                ended = previous_run.ended_at
                if ended.tzinfo is None:
                    ended = ended.replace(tzinfo=UTC)
                if now - ended < timedelta(minutes=settings.minimum_interval_minutes):
                    raise ValueError("Global discovery minimum interval has not elapsed")
                if now - ended > timedelta(hours=12):
                    catch_up_from = max(
                        ended,
                        now - timedelta(days=settings.catch_up_days),
                    )
            profile_projection_version = self._profile_projection(session)
            due_source_rows = session.scalars(
                select(SourceRegistryRow.id).where(
                    SourceRegistryRow.disabled.is_(False),
                    SourceRegistryRow.next_check_at.is_not(None),
                    SourceRegistryRow.next_check_at <= now,
                )
            ).all()
            metrics = _empty_metrics()
            metrics["source_checks"] = 0
            run = DiscoveryRunRow(
                id=new_id(),
                profile_projection_version=profile_projection_version,
                enabled_lenses=lenses,
                completed_lenses=[],
                skipped_lenses={},
                baseline_query_counts={lens: 0 for lens in lenses},
                metrics={
                    **metrics,
                    "source_checks_due": min(len(due_source_rows), settings.source_check_budget),
                    "allocation": allocations,
                },
                status="running",
                deep_contract_satisfied=False,
                delivery_result=None,
                errors=[],
                started_at=now,
                ended_at=None,
                catch_up_from=catch_up_from,
            )
            session.add(run)
            session.flush()
            branches: list[dict[str, Any]] = []
            for lens in lenses:
                strategy_rows = [
                    self._strategy(
                        session,
                        lens=lens,
                        template=template,
                        profile_projection_version=profile_projection_version,
                    )
                    for template in BASELINE_TEMPLATES[lens]
                ]
                branch = SearchBranchRow(
                    id=new_id(),
                    discovery_run_id=run.id,
                    scout_run_id=None,
                    parent_branch_id=None,
                    lens=lens,
                    allocation_class=lens_class(lens),
                    depth=0,
                    strategy_ids=[row.id for row in strategy_rows],
                    allocated_queries=allocations[lens],
                    queries_used=0,
                    recent_observations=[],
                    metrics=_empty_metrics(),
                    status="active",
                    stop_reason=None,
                    reallocated_queries=0,
                    started_at=now,
                    ended_at=None,
                )
                session.add(branch)
                session.flush()
                scout = self._scout_row(
                    run_id=run.id,
                    branch_id=branch.id,
                    lens=lens,
                    allocated_queries=allocations[lens],
                    started_at=now,
                )
                session.add(scout)
                session.flush()
                branch.scout_run_id = scout.id
                branches.append(self._branch_dict(branch, strategy_rows))
            result = {
                "run_id": run.id,
                "profile_projection_version": profile_projection_version,
                "lenses": lenses,
                "budgets": {
                    "max_queries": settings.max_queries,
                    "max_candidate_pages": settings.max_candidate_pages,
                    "max_deep_evaluations": settings.max_deep_evaluations,
                    "max_model_calls": settings.max_model_calls,
                    "max_duration_seconds": settings.max_duration_seconds,
                    "max_adaptive_depth": settings.max_adaptive_depth,
                },
                "catch_up_from": catch_up_from.isoformat() if catch_up_from else None,
                "branches": branches,
            }
            store_idempotent(session, idempotency_key, operation, result)
            audit(
                session,
                event_type="discovery_started",
                reason="global stateful discovery plan created",
                subject_type="discovery_run",
                subject_id=run.id,
                ruleset_version=DISCOVERY_RULESET_VERSION,
                details={"lens_count": len(lenses), "catch_up": bool(catch_up_from)},
            )
            return result

    def record_query(
        self,
        run_id: str,
        value: DiscoveryQueryInput,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "discovery.record_query"
        observation = DiscoveryQueryInput.model_validate(value)
        normalized_query = normalize_query(observation.query)
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            run = session.get(DiscoveryRunRow, run_id)
            branch = session.get(SearchBranchRow, observation.branch_id)
            strategy = session.get(QueryStrategyRow, observation.strategy_id)
            if run is None or branch is None or strategy is None:
                raise ValueError("Discovery run, branch, and strategy are required")
            if branch.discovery_run_id != run.id or strategy.id not in branch.strategy_ids:
                raise ValueError("Query observation does not belong to the requested branch")
            if branch.status != "active" or run.status not in {"running", "budget_stopped"}:
                raise ValueError("Discovery branch is not accepting observations")
            if branch.queries_used >= branch.allocated_queries:
                branch.status = "budget_stopped"
                branch.stop_reason = "branch query allocation exhausted"
                raise ValueError("Branch query allocation exhausted")
            now = utc_now()
            increments = observation.model_dump(exclude={"branch_id", "strategy_id", "query"})
            increments["queries"] = 1
            run_metrics = _add_metrics(run.metrics, increments)
            settings = self.context.settings.discovery
            hard_limit = (
                run_metrics["queries"] > settings.max_queries
                or run_metrics["pages"] > settings.max_candidate_pages
                or run_metrics["model_calls"] > settings.max_model_calls
                or run_metrics["deep_evaluated"] > settings.max_deep_evaluations
                or (
                    now - run.started_at.replace(tzinfo=run.started_at.tzinfo or UTC)
                ).total_seconds()
                > settings.max_duration_seconds
            )
            day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
            daily_runs = session.scalars(
                select(DiscoveryRunRow).where(DiscoveryRunRow.started_at >= day_start)
            ).all()
            if observation.model_calls:
                daily_model_calls = (
                    sum(int(item.metrics.get("model_calls", 0)) for item in daily_runs)
                    + observation.model_calls
                )
                hard_limit = hard_limit or daily_model_calls > settings.daily_model_calls
            daily_queries = sum(int(item.metrics.get("queries", 0)) for item in daily_runs) + 1
            hard_limit = hard_limit or daily_queries > settings.daily_queries
            run.metrics = run_metrics
            branch.metrics = _add_metrics(branch.metrics, increments)
            branch.queries_used += 1
            branch.recent_observations = [
                *branch.recent_observations,
                {
                    "raw": observation.raw,
                    "novel": observation.novel,
                    "qualified": observation.qualified,
                    "duplicate": observation.duplicate,
                },
            ][-50:]
            strategy_metrics = _add_metrics(strategy.metrics, increments)
            strategy.metrics = strategy_metrics
            strategy.use_count += 1
            strategy.first_used_at = strategy.first_used_at or now
            strategy.last_used_at = now
            strategy.historical_yield = deterministic_yield(
                raw=strategy_metrics["raw"],
                novel=strategy_metrics["novel"],
                official_verified=strategy_metrics["official_verified"],
                eligible=strategy_metrics["eligible"],
                apply=strategy_metrics["apply"],
                maybe=strategy_metrics["maybe"],
                duplicate=strategy_metrics["duplicate"],
                stale=strategy_metrics["stale"],
                closed=strategy_metrics["closed"],
                failures=strategy_metrics["failures"],
            )
            strategy.recent_yield = recent_yield(branch.recent_observations)
            strategy.updated_at = now
            if hard_limit:
                branch.status = "budget_stopped"
                branch.stop_reason = "global discovery budget exhausted"
                branch.ended_at = now
                run.status = "budget_stopped"
                run.metrics = _add_metrics(run.metrics, {"hard_budget_stops": 1})
                result = {
                    "run_id": run.id,
                    "branch_id": branch.id,
                    "strategy_id": strategy.id,
                    "stopped": True,
                    "reason": branch.stop_reason,
                    "normalized_query": normalized_query,
                    "metrics": branch.metrics,
                }
                store_idempotent(session, idempotency_key, operation, result)
                return result
            saturated, reason = saturation_decision(
                branch.recent_observations,
                queries_used=branch.queries_used,
                baseline=self.context.settings.discovery.baseline_min_query_families,
                no_novel_queries=settings.saturation_no_novel_queries,
                no_qualified_queries=settings.saturation_no_qualified_queries,
                duplicate_rate=settings.saturation_duplicate_rate,
                max_depth_reached=branch.depth >= settings.max_adaptive_depth,
                due_sources_complete=(
                    int(run.metrics.get("source_checks_due", 0)) > 0
                    and int(run.metrics.get("source_checks", 0))
                    >= int(run.metrics.get("source_checks_due", 0))
                ),
            )
            reallocated_to: str | None = None
            reallocated = 0
            if saturated and reason:
                branch.status = "saturated"
                branch.stop_reason = reason
                branch.ended_at = now
                run.metrics = _add_metrics(run.metrics, {"saturation_stops": 1})
                reallocated_to, reallocated = self._reallocate(session, run, branch)
            result = {
                "run_id": run.id,
                "branch_id": branch.id,
                "strategy_id": strategy.id,
                "stopped": bool(saturated),
                "reason": reason,
                "normalized_query": normalized_query,
                "metrics": branch.metrics,
                "historical_yield": strategy.historical_yield,
                "recent_yield": strategy.recent_yield,
                "reallocated_to": reallocated_to,
                "reallocated_queries": reallocated,
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def _reallocate(
        self,
        session: Any,
        run: DiscoveryRunRow,
        source: SearchBranchRow,
    ) -> tuple[str | None, int]:
        available = max(0, source.allocated_queries - source.queries_used)
        if available == 0:
            return None, 0
        candidates = session.scalars(
            select(SearchBranchRow).where(
                SearchBranchRow.discovery_run_id == run.id,
                SearchBranchRow.id != source.id,
                SearchBranchRow.status == "active",
            )
        ).all()
        if not candidates:
            return None, 0
        target = max(
            candidates,
            key=lambda item: (
                deterministic_yield(
                    raw=int(item.metrics.get("raw", 0)),
                    novel=int(item.metrics.get("novel", 0)),
                    official_verified=int(item.metrics.get("official_verified", 0)),
                    eligible=int(item.metrics.get("eligible", 0)),
                    apply=int(item.metrics.get("apply", 0)),
                    maybe=int(item.metrics.get("maybe", 0)),
                    duplicate=int(item.metrics.get("duplicate", 0)),
                    stale=int(item.metrics.get("stale", 0)),
                    closed=int(item.metrics.get("closed", 0)),
                    failures=int(item.metrics.get("failures", 0)),
                ),
                int(
                    item.queries_used < self.context.settings.discovery.baseline_min_query_families
                ),
                int(item.allocation_class == "exploratory"),
                item.lens,
            ),
        )
        target.allocated_queries += available
        source.reallocated_queries += available
        run.metrics = _add_metrics(
            run.metrics,
            {"budget_reallocations": 1, "reallocated_queries": available},
        )
        return target.id, available

    def expand_branch(
        self,
        run_id: str,
        proposal: DiscoveryExpansionInput,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "discovery.expand_branch"
        value = DiscoveryExpansionInput.model_validate(proposal)
        normalized = normalize_query(value.query)
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            run = session.get(DiscoveryRunRow, run_id)
            parent = session.get(SearchBranchRow, value.parent_branch_id)
            if run is None or parent is None or parent.discovery_run_id != run_id:
                raise ValueError("Discovery run and parent branch are required")
            settings = self.context.settings.discovery
            if parent.status != "active":
                raise ValueError("Only active branches can expand")
            depth = parent.depth + 1
            if depth > settings.max_adaptive_depth:
                raise ValueError("Adaptive branch depth limit reached")
            if value.lens not in self._enabled_lenses():
                raise ValueError("Adaptive branch lens is not enabled")
            if int(run.metrics.get("queries", 0)) >= settings.max_queries:
                raise ValueError("Global query budget is exhausted")
            branch_count = int(
                session.scalar(
                    select(func.count(SearchBranchRow.id)).where(
                        SearchBranchRow.discovery_run_id == run.id
                    )
                )
                or 0
            )
            if branch_count >= settings.max_queries:
                raise ValueError("Adaptive branch budget is exhausted")
            if (
                value.seed_opportunity_id
                and session.get(OpportunityRow, value.seed_opportunity_id) is None
            ):
                raise ValueError("Adaptive seed opportunity was not found")
            if value.seed_source_id and session.get(SourceRow, value.seed_source_id) is None:
                raise ValueError("Adaptive seed source was not found")
            strategy = self._strategy(
                session,
                lens=value.lens,
                template=normalized,
                profile_projection_version=run.profile_projection_version,
                parent_strategy_id=parent.strategy_ids[-1] if parent.strategy_ids else None,
                seed_opportunity_id=value.seed_opportunity_id,
                seed_source_id=value.seed_source_id,
                generation_reason=f"{value.trigger}: {value.generation_reason}",
            )
            now = utc_now()
            allocated = max(
                settings.baseline_min_query_families,
                min(10, settings.max_queries - int(run.metrics.get("queries", 0))),
            )
            branch = SearchBranchRow(
                id=new_id(),
                discovery_run_id=run.id,
                scout_run_id=None,
                parent_branch_id=parent.id,
                lens=value.lens,
                allocation_class=lens_class(value.lens),
                depth=depth,
                strategy_ids=[strategy.id],
                allocated_queries=allocated,
                queries_used=0,
                recent_observations=[],
                metrics=_empty_metrics(),
                status="active",
                stop_reason=None,
                reallocated_queries=0,
                started_at=now,
                ended_at=None,
            )
            session.add(branch)
            session.flush()
            scout = self._scout_row(
                run_id=run.id,
                branch_id=branch.id,
                lens=value.lens,
                allocated_queries=allocated,
                started_at=now,
            )
            session.add(scout)
            session.flush()
            branch.scout_run_id = scout.id
            run.metrics = _add_metrics(run.metrics, {"adaptive_branches": 1})
            result = {
                "run_id": run.id,
                "branch": self._branch_dict(branch, [strategy]),
                "strategy": self._strategy_dict(strategy),
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def record_source_check(
        self,
        run_id: str,
        value: DiscoverySourceCheckInput,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "discovery.record_source_check"
        source = DiscoverySourceCheckInput.model_validate(value)
        domain = canonical_source_domain(source.locator)
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            run = session.get(DiscoveryRunRow, run_id)
            if run is None or run.status not in {"running", "budget_stopped"}:
                raise ValueError("Active discovery run not found")
            if (
                int(run.metrics.get("source_checks", 0))
                >= self.context.settings.discovery.source_check_budget
            ):
                raise ValueError("Source-check budget exhausted")
            row = session.scalar(
                select(SourceRegistryRow).where(SourceRegistryRow.domain == domain)
            )
            now = utc_now()
            if row is None:
                row = SourceRegistryRow(
                    id=new_id(),
                    domain=domain,
                    canonical_name=self._safe_reason(source.canonical_name)[:300],
                    source_type=self._safe_reason(source.source_type)[:100],
                    official_or_secondary=source.official_or_secondary,
                    supported_lenses=sorted(set(source.supported_lenses)),
                    trust_class=self._safe_reason(source.trust_class)[:100],
                    first_seen_at=now,
                    last_checked_at=None,
                    next_check_at=None,
                    check_cadence_hours=source.check_cadence_hours,
                    successful_discovery_count=0,
                    apply_discovery_count=0,
                    maybe_discovery_count=0,
                    duplicate_count=0,
                    closed_or_stale_count=0,
                    failure_count=0,
                    recent_yield_score=0,
                    historical_yield_score=0,
                    change_frequency=0,
                    preferred_discovery_method=self._safe_reason(source.preferred_method)[:100],
                    disabled=source.disabled,
                    disabled_reason=self._safe_reason(source.disabled_reason or "") or None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            row.last_checked_at = now
            row.next_check_at = now + timedelta(hours=source.check_cadence_hours)
            row.supported_lenses = sorted(set(row.supported_lenses) | set(source.supported_lenses))
            row.successful_discovery_count += source.successful_discoveries
            row.apply_discovery_count += source.apply_discoveries
            row.maybe_discovery_count += source.maybe_discoveries
            row.duplicate_count += source.duplicates
            row.closed_or_stale_count += source.closed_or_stale
            row.failure_count += int(source.failed)
            row.disabled = source.disabled
            row.disabled_reason = self._safe_reason(source.disabled_reason or "") or None
            row.updated_at = now
            raw = (
                source.successful_discoveries
                + source.apply_discoveries
                + source.maybe_discoveries
                + source.duplicates
                + source.closed_or_stale
                + int(source.failed)
            )
            row.recent_yield_score = deterministic_yield(
                raw=raw,
                novel=source.successful_discoveries,
                apply=source.apply_discoveries,
                maybe=source.maybe_discoveries,
                duplicate=source.duplicates,
                stale=source.closed_or_stale,
                failures=int(source.failed),
            )
            row.historical_yield_score = round(
                (row.historical_yield_score * 0.8) + (row.recent_yield_score * 0.2), 2
            )
            row.change_frequency = round(
                (row.change_frequency * 0.8) + (0.2 if source.changed else 0), 2
            )
            run.metrics = _add_metrics(run.metrics, {"source_checks": 1})
            result = {
                "run_id": run.id,
                "source_id": row.id,
                "domain": row.domain,
                "next_check_at": row.next_check_at.isoformat(),
                "failed": source.failed,
                "recent_yield_score": row.recent_yield_score,
                "historical_yield_score": row.historical_yield_score,
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def finish(
        self,
        run_id: str,
        *,
        completed_lenses: list[str],
        skipped_lenses: dict[str, str],
        errors: list[str] | None = None,
        material_opportunity_ids: list[str] | None = None,
        dedup_completed: bool = True,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "discovery.finish"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            run = session.get(DiscoveryRunRow, run_id)
            if run is None or run.status not in {"running", "budget_stopped"}:
                raise ValueError("Finishable discovery run not found")
            enabled = set(run.enabled_lenses)
            completed = sorted(set(completed_lenses) & enabled)
            skipped = {
                lens: self._safe_reason(reason)
                for lens, reason in skipped_lenses.items()
                if lens in enabled
            }
            errors_safe = [self._safe_reason(error) for error in (errors or []) if error.strip()][
                :20
            ]
            run.completed_lenses = completed
            run.skipped_lenses = skipped
            run.errors = errors_safe
            branches = session.scalars(
                select(SearchBranchRow).where(SearchBranchRow.discovery_run_id == run.id)
            ).all()
            baseline_counts: dict[str, int] = {lens: 0 for lens in enabled}
            for branch in branches:
                baseline_counts[branch.lens] = baseline_counts.get(branch.lens, 0) + min(
                    branch.queries_used,
                    self.context.settings.discovery.baseline_min_query_families,
                )
                if branch.status == "active":
                    branch.status = "skipped" if branch.lens in skipped else "completed"
                    branch.ended_at = utc_now()
            run.baseline_query_counts = baseline_counts
            deliverable_ids = list(material_opportunity_ids or [])[
                : self.context.settings.discovery.max_notifications
            ]
            run.metrics = {
                **run.metrics,
                "dedup_completed": int(dedup_completed),
                "material_deliveries": len(deliverable_ids),
            }
            if len(material_opportunity_ids or []) > len(deliverable_ids):
                run.metrics = _add_metrics(run.metrics, {"hard_budget_stops": 1})
                run.status = "budget_stopped"
            official_verified = int(run.metrics.get("official_verified", 0))
            deep_evaluated = int(run.metrics.get("deep_evaluated", 0))
            deep_contract = coverage_contract(
                enabled_lenses=enabled,
                completed_lenses=completed,
                skipped_lenses=skipped,
                baseline_counts=baseline_counts,
                baseline_floor=self.context.settings.discovery.baseline_min_query_families,
                source_checks_due=int(run.metrics.get("source_checks_due", 0)),
                source_checks_completed=int(run.metrics.get("source_checks", 0)),
                adaptive_triggered=int(run.metrics.get("adaptive_branches", 0)) > 0,
                dedup_completed=dedup_completed,
                official_verified=official_verified,
                deep_evaluated=deep_evaluated,
                hard_failure=bool(errors_safe) or run.status == "budget_stopped",
            )
            run.deep_contract_satisfied = deep_contract
            run.ended_at = utc_now()
            run.delivery_result = "digest" if deliverable_ids else "silent"
            run.status = "success" if deep_contract and not errors_safe else "partial"
            if run.status == "partial" and run.metrics.get("hard_budget_stops", 0):
                run.status = "budget_stopped"
            audit(
                session,
                event_type="discovery_finished",
                reason="global discovery coverage finalized",
                subject_type="discovery_run",
                subject_id=run.id,
                ruleset_version=DISCOVERY_RULESET_VERSION,
                details={
                    "deep_contract_satisfied": deep_contract,
                    "delivery": run.delivery_result,
                    "skipped_lenses": sorted(skipped),
                },
            )
            result = self._run_dict(run)
            assert result is not None
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def coverage(self, run_id: str) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            run = session.get(DiscoveryRunRow, run_id)
            if run is None:
                raise ValueError("Discovery run not found")
            branches = session.scalars(
                select(SearchBranchRow)
                .where(SearchBranchRow.discovery_run_id == run.id)
                .order_by(SearchBranchRow.lens, SearchBranchRow.depth)
            ).all()
            result = self._run_dict(run)
            assert result is not None
            result["branches"] = [self._branch_dict(branch, []) for branch in branches]
            return result

    def strategies(self, *, lens: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("Strategy limit must be between 1 and 200")
        with self.context.database.transaction() as session:
            query = select(QueryStrategyRow).order_by(
                QueryStrategyRow.recent_yield.desc(), QueryStrategyRow.last_used_at.desc()
            )
            if lens:
                query = query.where(QueryStrategyRow.lens == lens)
            rows = session.scalars(query.limit(limit)).all()
            return [self._strategy_dict(row) for row in rows]

    def sources(self, *, due_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("Source limit must be between 1 and 200")
        with self.context.database.transaction() as session:
            query = select(SourceRegistryRow).order_by(
                SourceRegistryRow.recent_yield_score.desc(), SourceRegistryRow.next_check_at
            )
            if due_only:
                query = query.where(
                    SourceRegistryRow.disabled.is_(False),
                    SourceRegistryRow.next_check_at <= utc_now(),
                )
            rows = session.scalars(query.limit(limit)).all()
            return [self._source_dict(row) for row in rows]

    def status(self) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            latest = session.scalar(
                select(DiscoveryRunRow).order_by(DiscoveryRunRow.started_at.desc())
            )
            return {
                "enabled": self.context.settings.discovery.enabled,
                "schedules": self.context.settings.discovery.schedules,
                "latest_run": self._run_dict(latest) if latest else None,
                "strategy_count": len(session.scalars(select(QueryStrategyRow.id)).all()),
                "source_count": len(session.scalars(select(SourceRegistryRow.id)).all()),
                "active_branch_count": len(
                    session.scalars(
                        select(SearchBranchRow.id).where(SearchBranchRow.status == "active")
                    ).all()
                ),
            }

    @staticmethod
    def _strategy_dict(row: QueryStrategyRow) -> dict[str, Any]:
        return {
            "strategy_id": row.id,
            "lens": row.lens,
            "query_family": row.query_family,
            "query_template": row.query_template,
            "parent_strategy_id": row.parent_strategy_id,
            "seed_opportunity_id": row.seed_opportunity_id,
            "seed_source_id": row.seed_source_id,
            "generation_reason": row.generation_reason,
            "use_count": row.use_count,
            "metrics": row.metrics,
            "historical_yield": row.historical_yield,
            "recent_yield": row.recent_yield,
            "disabled": row.disabled,
            "disabled_reason": row.disabled_reason,
        }

    @classmethod
    def _branch_dict(
        cls, row: SearchBranchRow, strategies: list[QueryStrategyRow]
    ) -> dict[str, Any]:
        return {
            "branch_id": row.id,
            "scout_run_id": row.scout_run_id,
            "parent_branch_id": row.parent_branch_id,
            "lens": row.lens,
            "allocation_class": row.allocation_class,
            "depth": row.depth,
            "strategy_ids": row.strategy_ids,
            "strategies": [cls._strategy_dict(strategy) for strategy in strategies],
            "allocated_queries": row.allocated_queries,
            "queries_used": row.queries_used,
            "status": row.status,
            "stop_reason": row.stop_reason,
            "metrics": row.metrics,
            "reallocated_queries": row.reallocated_queries,
        }

    @staticmethod
    def _source_dict(row: SourceRegistryRow) -> dict[str, Any]:
        return {
            "source_id": row.id,
            "domain": row.domain,
            "canonical_name": row.canonical_name,
            "source_type": row.source_type,
            "official_or_secondary": row.official_or_secondary,
            "supported_lenses": row.supported_lenses,
            "trust_class": row.trust_class,
            "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
            "next_check_at": row.next_check_at.isoformat() if row.next_check_at else None,
            "check_cadence_hours": row.check_cadence_hours,
            "successful_discovery_count": row.successful_discovery_count,
            "apply_discovery_count": row.apply_discovery_count,
            "maybe_discovery_count": row.maybe_discovery_count,
            "duplicate_count": row.duplicate_count,
            "closed_or_stale_count": row.closed_or_stale_count,
            "recent_yield_score": row.recent_yield_score,
            "historical_yield_score": row.historical_yield_score,
            "change_frequency": row.change_frequency,
            "preferred_discovery_method": row.preferred_discovery_method,
            "disabled": row.disabled,
            "disabled_reason": row.disabled_reason,
            "failure_count": row.failure_count,
        }

    @staticmethod
    def _run_dict(row: DiscoveryRunRow | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "run_id": row.id,
            "profile_projection_version": row.profile_projection_version,
            "enabled_lenses": row.enabled_lenses,
            "completed_lenses": row.completed_lenses,
            "skipped_lenses": row.skipped_lenses,
            "baseline_query_counts": row.baseline_query_counts,
            "metrics": row.metrics,
            "status": row.status,
            "deep_contract_satisfied": row.deep_contract_satisfied,
            "delivery_result": row.delivery_result,
            "errors": row.errors,
            "started_at": row.started_at.isoformat(),
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "catch_up_from": row.catch_up_from.isoformat() if row.catch_up_from else None,
        }
