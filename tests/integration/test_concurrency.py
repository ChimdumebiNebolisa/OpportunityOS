from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from opportunityos.application.context import ApplicationContext
from opportunityos.application.opportunities import OpportunityService
from opportunityos.infrastructure.database import OpportunityRow
from opportunityos.schemas import (
    OfficialStatus,
    OpportunityInput,
    SourceCreate,
    SourceType,
)


def test_concurrent_duplicate_intake_converges_to_one_record(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    data_dir = tmp_path / "private-data"
    config_dir = tmp_path / "private-config"
    first_context = ApplicationContext.create(repository, data_dir=data_dir, config_dir=config_dir)
    second_context = ApplicationContext.create(repository, data_dir=data_dir, config_dir=config_dir)
    source_id = OpportunityService(first_context).add_source(
        SourceCreate(
            source_type=SourceType.OFFICIAL_WEBPAGE,
            source_locator="https://example.org/concurrent",
            display_name="Synthetic concurrent fixture",
            official_status=OfficialStatus.OFFICIAL,
            retrieved_at=datetime.now(UTC),
            content_hash="c" * 64,
            mime_type="text/html",
            trust_class="official",
        )
    )
    value = OpportunityInput(
        canonical_title="Concurrent Synthetic Scholarship",
        organization="Synthetic Foundation",
        opportunity_type="scholarship",
        cycle="2027",
        canonical_url="https://example.org/concurrent",
        application_url="https://example.org/concurrent/apply",
        deadline_at=datetime.now(UTC) + timedelta(days=20),
        deadline_timezone="UTC",
        open_status="open",
        source_completeness=1,
        source_ids=[source_id],
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(OpportunityService(context).submit_opportunity, value)
            for context in (first_context, second_context)
        ]
        results = [future.result(timeout=10) for future in futures]

    assert {result["duplicate"] for result in results} == {False, True}
    assert len({result["opportunity_id"] for result in results}) == 1
    with first_context.database.transaction() as session:
        count = session.scalar(select(func.count()).select_from(OpportunityRow))
    assert count == 1
