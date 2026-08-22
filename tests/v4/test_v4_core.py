from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from opportunityos.v4.dedupe import fingerprint, normalize_url
from opportunityos.v4.export import export_state, import_state
from opportunityos.v4.runtime import RuntimePaths, write_yaml
from opportunityos.v4.store import HistoryStore


def _store(tmp_path: Path, name: str = "one") -> tuple[RuntimePaths, HistoryStore]:
    paths = RuntimePaths(tmp_path / name, tmp_path / "repository")
    store = HistoryStore(paths)
    store.initialize()
    return paths, store


def _candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "title": "Example Fellowship",
        "organization": "Example Org",
        "category": "fellowship",
        "source_url": "https://example.org/program?utm_source=agent",
        "official_url": "https://example.org/program",
        "application_url": "https://example.org/app",
        "status": "open",
        "first_party": True,
        "verified_at": "2026-08-22T17:00:00Z",
        "metadata": {"cycle": "2026"},
    }
    value.update(overrides)
    return value


def test_normalization_and_fingerprint_are_stable() -> None:
    assert normalize_url("HTTPS://Example.ORG/a/?utm_medium=x&b=2#top") == (
        "https://example.org/a?b=2"
    )
    assert fingerprint("Example Org", "Example Fellowship", "fellowship", {"year": 2026}) == (
        fingerprint(" example-org ", "example fellowship", "FELLOWSHIP", {"year": 2026})
    )


def test_search_run_deduplicates_and_records_feedback(tmp_path: Path) -> None:
    _, store = _store(tmp_path)
    run = store.start_run("fellowship", "hermes", "model-a")
    first = store.record_candidate(
        run["run_id"], _candidate(), query="fellowship 2026", source="example.org"
    )
    duplicate = store.check_candidate(_candidate())
    recorded_duplicate = store.record_candidate(run["run_id"], _candidate())

    assert first["is_new"] is True
    assert duplicate["is_new"] is False
    assert recorded_duplicate["is_new"] is False
    store.add_feedback(
        {"opportunity_id": first["opportunity_id"], "type": "useful", "text": "Keep this source."}
    )
    finished = store.finish_run(run["run_id"], {"query_count": 1, "delivered_count": 1})
    assert finished["candidate_count"] == 2
    assert store.context("fellowship")["recent_history"]["recent_feedback_summary"] == {"useful": 1}


def test_material_change_and_policy_rejection(tmp_path: Path) -> None:
    paths, store = _store(tmp_path)
    run = store.start_run("jobs", "agent", "model")
    old = datetime.now(UTC) - timedelta(days=5)
    write_yaml(
        paths.policy,
        {
            "version": 1,
            "global": {"require_official_verification": False},
            "categories": {
                "jobs": {"freshness": {"maximum_age_hours": 24, "unknown_age": "reject"}}
            },
        },
    )
    stale = _candidate(
        category="jobs", published_at=old.isoformat(), official_url=None, first_party=None
    )
    result = store.check_candidate(stale)
    assert result["policy_result"] == "reject"
    assert "published_at:too_old" in result["violations"]

    write_yaml(paths.policy, {"version": 1, "global": {"require_official_verification": False}})
    first = store.record_candidate(run["run_id"], _candidate(status="closed"))
    reopened = store.check_candidate(_candidate(status="open"))
    assert first["is_new"] is True
    assert reopened["is_new"] is True
    assert reopened["material_change"] is True


def test_strategy_learning_rejects_protected_fields_and_rolls_back(tmp_path: Path) -> None:
    _, store = _store(tmp_path)
    with pytest.raises(ValueError, match="protected"):
        store.propose_strategy(
            {
                "reason": "unsafe",
                "evidence": ["feedback-1"],
                "scope": "global",
                "changes": {"policy": {"global": {"reject_closed": False}}},
                "proposed_by": "agent",
            }
        )
    accepted = store.propose_strategy(
        {
            "reason": "Example Org repeatedly yielded verified results.",
            "evidence": ["run-1", "feedback-1"],
            "scope": "fellowship",
            "changes": {"preferred_sources": ["example.org"]},
            "proposed_by": "agent",
            "model": "model-a",
        }
    )
    assert accepted["accepted"] is True
    assert store.strategy_show()["categories"]["fellowship"]["preferred_sources"] == ["example.org"]
    rollback = store.rollback_strategy(1)
    assert rollback["rolled_back_to"] == 1
    assert "fellowship" not in store.strategy_show().get("categories", {})


def test_export_import_preserves_state(tmp_path: Path) -> None:
    paths, store = _store(tmp_path, "source")
    run = store.start_run("fellowship", "hermes", "model-a")
    store.record_candidate(run["run_id"], _candidate())
    archive = tmp_path / "export.zip"
    export_state(paths, archive)

    imported_paths, imported = _store(tmp_path, "destination")
    import_state(imported_paths, archive)
    assert imported.context("fellowship")["recent_history"]["seen_urls"] == [
        "https://example.org/program"
    ]
    assert imported.recent_history()[0]["title"] == "Example Fellowship"
