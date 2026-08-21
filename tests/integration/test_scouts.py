from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from opportunityos.application.decisions import DecisionService
from opportunityos.application.opportunities import OpportunityService
from opportunityos.application.scouts import ScoutService
from opportunityos.infrastructure.database import ScoutRunRow
from opportunityos.schemas import ScoutRunInput
from tests.e2e.test_core_workflows import _assess, _seed, _source


def _run_input(context: Any) -> ScoutRunInput:
    return ScoutRunInput(
        category="scholarship",
        query_plan=["synthetic scholarship official international"],
        budget=context.settings.scouts.model_dump(),
    )


def test_quiet_run_and_budget_stop(context_factory: Any) -> None:
    context = context_factory()
    service = ScoutService(context)
    started = service.begin(_run_input(context))
    usage = service.record_usage(started["run_id"], queries=context.settings.scouts.max_queries + 1)
    assert usage["stopped"] is True
    finished = service.finish(started["run_id"], material_opportunity_ids=[])
    assert finished["delivery_result"] == "silent"
    assert finished["digest"] is None
    assert finished["status"] == "budget_stopped"


def test_laptop_gap_creates_catch_up_window(context_factory: Any) -> None:
    context = context_factory()
    service = ScoutService(context)
    first = service.begin(_run_input(context))
    service.finish(first["run_id"], material_opportunity_ids=[])
    with context.database.transaction() as session:
        row = session.get(ScoutRunRow, first["run_id"])
        assert row is not None
        row.ended_at = datetime.now(UTC) - timedelta(days=3)
    second = service.begin(_run_input(context))
    assert second["catch_up_from"] is not None


def test_strong_candidate_digest_status_and_usage_guards(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=20,
        next_action_minutes=10,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    service = ScoutService(context)
    started = service.begin(_run_input(context), idempotency_key="scout-start")
    assert service.begin(_run_input(context), idempotency_key="scout-start") == started
    usage = service.record_usage(started["run_id"], queries=1, pages=2, model_calls=1)
    assert usage["queries"] == 1 and usage["stopped"] is False
    candidate = service.record_candidate(started["run_id"], opportunity_id, source_ids=[source_id])
    assert candidate["strong"] is True
    finished = service.finish(
        started["run_id"],
        material_opportunity_ids=[opportunity_id, "not-a-candidate"],
        idempotency_key="scout-finish",
    )
    assert finished["delivery_result"] == "digest"
    assert finished["material_opportunity_ids"] == [opportunity_id]
    assert (
        service.finish(
            started["run_id"],
            material_opportunity_ids=[],
            idempotency_key="scout-finish",
        )
        == finished
    )
    assert service.status()[0]["status"] == "success"
    with pytest.raises(ValueError, match="negative"):
        service.record_usage(started["run_id"], queries=-1)
    with pytest.raises(ValueError, match="Running scout"):
        service.record_usage("missing", queries=1)

    repeated = service.begin(_run_input(context))
    assert (
        service.record_candidate(repeated["run_id"], opportunity_id, source_ids=[source_id])[
            "strong"
        ]
        is False
    )
    repeated_finish = service.finish(repeated["run_id"], material_opportunity_ids=[opportunity_id])
    assert repeated_finish["delivery_result"] == "silent"


def test_weak_and_unknown_candidates_never_reach_digest(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, _fact_id, source_id = _seed(context)
    service = ScoutService(context)
    started = service.begin(_run_input(context))
    with pytest.raises(ValueError, match="unknown sources"):
        service.record_candidate(started["run_id"], opportunity_id, source_ids=["missing"])
    unrelated_source = _source(
        OpportunityService(context), "https://example.org/unrelated", official=True
    )
    with pytest.raises(ValueError, match="not attached"):
        service.record_candidate(started["run_id"], opportunity_id, source_ids=[unrelated_source])
    assert service.record_candidate(started["run_id"], opportunity_id, source_ids=[source_id]) == {
        "opportunity_id": opportunity_id,
        "strong": False,
    }
    finished = service.finish(started["run_id"], material_opportunity_ids=[opportunity_id])
    assert finished["delivery_result"] == "silent"
    assert finished["material_opportunity_ids"] == []
    assert finished["digest"] is None


def test_daily_model_call_cap_spans_runs(context_factory: Any) -> None:
    context = context_factory()
    context.settings.scouts.daily_model_calls = 1
    service = ScoutService(context)
    first = service.begin(_run_input(context))
    assert service.record_usage(first["run_id"], model_calls=1)["stopped"] is False
    service.finish(first["run_id"], material_opportunity_ids=[])

    second = service.begin(_run_input(context))
    stopped = service.record_usage(second["run_id"], model_calls=1)
    assert stopped["stopped"] is True
    assert stopped["reason"] == "Daily scout model-call budget reached"
