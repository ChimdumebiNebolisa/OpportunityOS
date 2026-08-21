from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sqlalchemy import func, select

from opportunityos.application.context import ApplicationContext
from opportunityos.application.profile import ProfileService
from opportunityos.infrastructure.database import OpportunityRow
from opportunityos.mcp.server import (
    mcp,
    opportunity_submit_extraction,
    opportunity_submit_source,
)


def test_mcp_catalog_is_typed_and_has_no_external_actions() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    required = {
        "profile_get_current",
        "profile_submit_observations",
        "review_resolve",
        "opportunity_submit_input",
        "opportunity_submit_extraction",
        "eligibility_evaluate",
        "assessment_submit",
        "evaluation_compute",
        "queue_next",
        "application_prepare_context",
        "application_prepare",
        "application_store_artifact",
        "application_mark_ready",
        "scout_begin",
        "scout_record_usage",
        "scout_finish",
        "system_status",
        "backup_create",
    }
    assert required <= names
    assert all(tool.inputSchema.get("type") == "object" for tool in tools)
    prohibited = {"send", "submit_external", "post", "purchase", "accept_terms", "delete_remote"}
    assert not any(any(token in name for token in prohibited) for name in names)


def test_every_skill_tool_reference_exists() -> None:
    tools = {tool.name for tool in asyncio.run(mcp.list_tools())}
    pattern = re.compile(
        r"`((?:profile_(?:get|submit|rebuild|sync)|review_(?:list|get|resolve|defer)|"
        r"opportunity_(?:submit|get|find|reverify)|eligibility_evaluate|assessment_submit|"
        r"evaluation_(?:compute|get)|queue_(?:list|next)|action_(?:create|complete|skip)|"
        r"application_(?:create|prepare|store|mark)|lifecycle_update|"
        r"scout_(?:begin|record|finish)|system_status|backup_create)[a-z_]*)`"
    )
    root = Path(__file__).parents[2] / "skills"
    referenced: set[str] = set()
    for skill_path in root.glob("*/SKILL.md"):
        text = skill_path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "untrusted data" in lowered or "source instructions" in lowered
        assert "SQLite" in text or "MCP" in text or "mcp" in text.lower()
        referenced.update(pattern.findall(text))
    assert referenced
    assert referenced <= tools


def test_skill_metadata_has_no_placeholders() -> None:
    root = Path(__file__).parents[2] / "skills"
    for skill_path in root.glob("*/SKILL.md"):
        text = skill_path.read_text(encoding="utf-8")
        assert "TODO" not in text
        assert text.startswith("---\nname: opportunityos-")


def test_generic_mcp_source_submission_cannot_assert_official_status() -> None:
    result = opportunity_submit_source(
        {
            "source_type": "official_webpage",
            "source_locator": "https://example.org/synthetic",
            "display_name": "Synthetic source",
            "official_status": "official",
            "retrieved_at": "2026-08-21T00:00:00Z",
            "content_hash": "d" * 64,
            "trust_class": "official",
        },
        "synthetic-official-spoof",
    )
    assert result["ok"] is False
    assert result["error_code"] == "INVALID_INPUT"
    assert "opportunity_reverify" in result["error"]

    trust_spoof = opportunity_submit_source(
        {
            "source_type": "local_document",
            "source_locator": "private:synthetic",
            "display_name": "Synthetic trust spoof",
            "official_status": "unknown",
            "retrieved_at": "2026-08-21T00:00:00Z",
            "content_hash": "e" * 64,
            "trust_class": "official_record",
        },
        "synthetic-trust-spoof",
    )
    assert trust_spoof["ok"] is False
    assert "opportunity_reverify" in trust_spoof["error"]


def test_invalid_extraction_repairs_once_then_records_review_without_partial_state(
    monkeypatch: object, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.chdir(repository)  # type: ignore[attr-defined]
    monkeypatch.setenv("OPPORTUNITYOS_DATA_DIR", str(tmp_path / "private"))  # type: ignore[attr-defined]
    monkeypatch.setenv("OPPORTUNITYOS_CONFIG_DIR", str(tmp_path / "config"))  # type: ignore[attr-defined]
    invalid = {"canonical_title": "Missing required fields"}

    first = opportunity_submit_extraction(invalid, [], "invalid-extraction", repair_attempt=0)
    assert first["ok"] is False
    assert "retry once" in first["error"]
    second = opportunity_submit_extraction(invalid, [], "invalid-extraction", repair_attempt=1)
    assert second["ok"] is False
    assert "review item" in second["error"]

    context = ApplicationContext.create(repository)
    reviews = ProfileService(context).list_reviews()
    assert len(reviews) == 1
    assert reviews[0]["review_type"] == "source_failure"
    with context.database.transaction() as session:
        opportunity_count = session.scalar(select(func.count()).select_from(OpportunityRow))
    assert opportunity_count == 0
