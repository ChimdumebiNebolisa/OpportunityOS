"""Small SQLite history store used by the v4 agent protocol."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast

from .dedupe import fingerprint, normalize_url
from .models import Candidate, FeedbackInput, StrategyProposal
from .policy import evaluate_candidate
from .runtime import RuntimePaths, merge_mappings, read_yaml, write_yaml

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _new_id() -> str:
    return str(uuid.uuid4())


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS opportunities (
  id TEXT PRIMARY KEY,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  organization TEXT NOT NULL,
  category TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_verified_at TEXT,
  status TEXT NOT NULL,
  deadline TEXT,
  source_url TEXT NOT NULL,
  official_url TEXT,
  fingerprint TEXT NOT NULL,
  metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunities_url ON opportunities(canonical_url);
CREATE INDEX IF NOT EXISTS idx_opportunities_fingerprint ON opportunities(fingerprint);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  agent TEXT,
  model TEXT,
  category TEXT NOT NULL,
  query_count INTEGER NOT NULL DEFAULT 0,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  verified_count INTEGER NOT NULL DEFAULT 0,
  delivered_count INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discoveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id),
  opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
  query TEXT,
  source TEXT,
  rank INTEGER,
  outcome TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_discoveries_run ON discoveries(run_id);
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  opportunity_id TEXT REFERENCES opportunities(id),
  run_id TEXT REFERENCES runs(id),
  type TEXT NOT NULL,
  reason TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_revisions (
  revision INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  diff_json TEXT NOT NULL,
  agent TEXT NOT NULL,
  model TEXT,
  previous_revision INTEGER,
  strategy_json TEXT NOT NULL
);
"""


class HistoryStore:
    """Own SQLite history and the durable strategy revision log."""

    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self.paths.ensure_initialized()
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            current = connection.execute("PRAGMA user_version").fetchone()[0]
            if current not in (0, SCHEMA_VERSION):
                raise RuntimeError(f"Unsupported state database version: {current}")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            if connection.execute("SELECT 1 FROM strategy_revisions LIMIT 1").fetchone() is None:
                strategy = read_yaml(self.paths.strategy)
                connection.execute(
                    """INSERT INTO strategy_revisions
                    (revision, created_at, reason, evidence_json, diff_json, agent,
                     model, previous_revision, strategy_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        1,
                        utc_now(),
                        "initial strategy",
                        "[]",
                        "{}",
                        "system",
                        None,
                        None,
                        _json(strategy),
                    ),
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.paths.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # A single portable database file keeps ZIP export/import deterministic.
        connection.execute("PRAGMA journal_mode = DELETE")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def start_run(
        self,
        category: str,
        agent: str | None,
        model: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        run_id = _new_id()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO runs
                (id, started_at, agent, model, category, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, utc_now(), agent, model, category, _json(metadata or {})),
            )
        return {"schema_version": 1, "run_id": run_id, "category": category}

    def _candidate_data(self, candidate: Candidate) -> tuple[dict[str, Any], str, str]:
        data = candidate.model_dump(mode="json")
        canonical = normalize_url(candidate.source_url)
        data["source_url"] = canonical
        if candidate.official_url:
            data["official_url"] = normalize_url(candidate.official_url)
        if candidate.application_url:
            data["application_url"] = normalize_url(candidate.application_url)
        candidate_fingerprint = fingerprint(
            candidate.organization, candidate.title, candidate.category, candidate.metadata
        )
        return data, canonical, candidate_fingerprint

    def _existing(
        self, connection: sqlite3.Connection, canonical_url: str, candidate_fingerprint: str
    ) -> sqlite3.Row | None:
        row = cast(
            sqlite3.Row | None,
            connection.execute(
                """SELECT * FROM opportunities WHERE canonical_url = ?
                ORDER BY last_seen_at DESC LIMIT 1""",
                (canonical_url,),
            ).fetchone(),
        )
        if row is not None:
            return row
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """SELECT * FROM opportunities WHERE fingerprint = ?
                ORDER BY last_seen_at DESC LIMIT 1""",
                (candidate_fingerprint,),
            ).fetchone(),
        )

    @staticmethod
    def _material_change(existing: sqlite3.Row, data: dict[str, Any]) -> bool:
        old_metadata = _decode(existing["metadata_json"], {})
        new_metadata = data.get("metadata", {})
        return any(
            (
                existing["status"] != data.get("status", "open"),
                existing["deadline"] != data.get("deadline"),
                existing["official_url"] != data.get("official_url"),
                old_metadata.get("eligibility") != data.get("eligibility"),
                old_metadata.get("metadata", {}).get("cycle") != new_metadata.get("cycle"),
                old_metadata.get("metadata", {}).get("year") != new_metadata.get("year"),
            )
        )

    def check_candidate(
        self, candidate_value: dict[str, Any] | Candidate, *, now: datetime | None = None
    ) -> dict[str, Any]:
        self.initialize()
        candidate = (
            candidate_value
            if isinstance(candidate_value, Candidate)
            else Candidate.model_validate(candidate_value)
        )
        data, canonical, candidate_fingerprint = self._candidate_data(candidate)
        policy_result = evaluate_candidate(data, read_yaml(self.paths.policy), now=now)
        with self._connect() as connection:
            existing = self._existing(connection, canonical, candidate_fingerprint)
        material = bool(existing and self._material_change(existing, data))
        return {
            "schema_version": 1,
            "is_new": existing is None or material,
            "duplicate_of": existing["id"] if existing else None,
            "material_change": material,
            **policy_result,
        }

    def record_candidate(
        self,
        run_id: str,
        candidate_value: dict[str, Any] | Candidate,
        *,
        query: str | None = None,
        source: str | None = None,
        rank: int | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        candidate = (
            candidate_value
            if isinstance(candidate_value, Candidate)
            else Candidate.model_validate(candidate_value)
        )
        data, canonical, candidate_fingerprint = self._candidate_data(candidate)
        policy_result = evaluate_candidate(data, read_yaml(self.paths.policy))
        now = utc_now()
        with self._lock, self._connect() as connection:
            if connection.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is None:
                raise ValueError("Run not found")
            existing = self._existing(connection, canonical, candidate_fingerprint)
            material = bool(existing and self._material_change(existing, data))
            is_new = existing is None or material
            if existing is None:
                opportunity_id = _new_id()
                connection.execute(
                    """INSERT INTO opportunities
                    (id, canonical_url, title, organization, category, first_seen_at,
                     last_seen_at, last_verified_at, status, deadline, source_url,
                     official_url, fingerprint, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        opportunity_id,
                        canonical,
                        data["title"],
                        data["organization"],
                        data["category"],
                        now,
                        now,
                        data.get("verified_at"),
                        data.get("status", "open"),
                        data.get("deadline"),
                        canonical,
                        data.get("official_url"),
                        candidate_fingerprint,
                        _json(data),
                    ),
                )
            else:
                opportunity_id = existing["id"]
                if material:
                    connection.execute(
                        """UPDATE opportunities SET last_seen_at = ?, last_verified_at = ?,
                        status = ?, deadline = ?, official_url = ?, metadata_json = ?
                        WHERE id = ?""",
                        (
                            now,
                            data.get("verified_at"),
                            data.get("status", "open"),
                            data.get("deadline"),
                            data.get("official_url"),
                            _json(data),
                            opportunity_id,
                        ),
                    )
                else:
                    connection.execute(
                        "UPDATE opportunities SET last_seen_at = ? WHERE id = ?",
                        (now, opportunity_id),
                    )
            outcome = (
                "policy_rejected"
                if policy_result["policy_result"] == "reject"
                else (
                    "material_change" if material else ("new" if existing is None else "duplicate")
                )
            )
            connection.execute(
                """INSERT INTO discoveries
                (run_id, opportunity_id, query, source, rank, outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, opportunity_id, query, source, rank, outcome, now),
            )
        return {
            "schema_version": 1,
            "opportunity_id": opportunity_id,
            "recorded": True,
            "is_new": is_new,
            "duplicate_of": existing["id"] if existing else None,
            "material_change": material,
            **policy_result,
        }

    def add_feedback(self, value: dict[str, Any] | FeedbackInput) -> dict[str, Any]:
        self.initialize()
        feedback = (
            value if isinstance(value, FeedbackInput) else FeedbackInput.model_validate(value)
        )
        with self._lock, self._connect() as connection:
            if (
                feedback.opportunity_id
                and connection.execute(
                    "SELECT 1 FROM opportunities WHERE id = ?", (feedback.opportunity_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("Opportunity not found")
            if (
                feedback.run_id
                and connection.execute(
                    "SELECT 1 FROM runs WHERE id = ?", (feedback.run_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("Run not found")
            feedback_id = _new_id()
            connection.execute(
                """INSERT INTO feedback
                (id, opportunity_id, run_id, type, reason, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id,
                    feedback.opportunity_id,
                    feedback.run_id,
                    feedback.type,
                    feedback.reason,
                    feedback.text,
                    utc_now(),
                ),
            )
        return {"schema_version": 1, "feedback_id": feedback_id, "type": feedback.type}

    def finish_run(self, run_id: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        self.initialize()
        summary = summary or {}
        with self._lock, self._connect() as connection:
            if connection.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is None:
                raise ValueError("Run not found")
            counts = connection.execute(
                """SELECT COUNT(*) AS candidates,
                SUM(CASE WHEN outcome IN ('new', 'material_change') THEN 1 ELSE 0 END) AS new_count
                FROM discoveries WHERE run_id = ?""",
                (run_id,),
            ).fetchone()
            values = (
                summary.get("query_count", 0),
                counts["candidates"] or 0,
                counts["new_count"] or 0,
                summary.get("verified_count", 0),
                summary.get("delivered_count", 0),
                utc_now(),
                _json(summary),
                run_id,
            )
            connection.execute(
                """UPDATE runs SET query_count = ?, candidate_count = ?, new_count = ?,
                verified_count = ?, delivered_count = ?, finished_at = ?, metadata_json = ?
                WHERE id = ?""",
                values,
            )
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return {"schema_version": 1, **dict(row)}

    def recent_history(self, query: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        self.initialize()
        pattern = f"%{query}%" if query else None
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM opportunities
                WHERE (? IS NULL OR title LIKE ? OR organization LIKE ? OR category LIKE ?)
                ORDER BY last_seen_at DESC LIMIT ?""",
                (pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._opportunity_dict(row) for row in rows]

    @staticmethod
    def _opportunity_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["metadata"] = _decode(result.pop("metadata_json"), {})
        return result

    def context(self, category: str) -> dict[str, Any]:
        self.initialize()
        profile = read_yaml(self.paths.profile)
        policy = read_yaml(self.paths.policy)
        strategy = read_yaml(self.paths.strategy)
        category_strategy = strategy.get("categories", {}).get(category, {})
        with self._connect() as connection:
            seen = connection.execute(
                """SELECT canonical_url FROM opportunities WHERE category = ?
                ORDER BY last_seen_at DESC LIMIT 100""",
                (category,),
            ).fetchall()
            organizations = connection.execute(
                """SELECT organization FROM opportunities
                WHERE category = ? GROUP BY organization
                ORDER BY MAX(last_seen_at) DESC LIMIT 20""",
                (category,),
            ).fetchall()
            feedback_rows = connection.execute(
                "SELECT type, COUNT(*) AS count FROM feedback GROUP BY type ORDER BY count DESC"
            ).fetchall()
            source_rows = connection.execute(
                """SELECT COALESCE(d.source, '') AS source,
                COUNT(DISTINCT d.run_id) AS runs, COUNT(d.id) AS candidates,
                SUM(CASE WHEN d.outcome IN ('new', 'material_change')
                    THEN 1 ELSE 0 END) AS new_count,
                SUM(CASE WHEN o.last_verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified,
                SUM(CASE WHEN d.outcome = 'policy_rejected' THEN 1 ELSE 0 END) AS rejected
                FROM discoveries d JOIN opportunities o ON o.id = d.opportunity_id
                GROUP BY d.source ORDER BY candidates DESC LIMIT 50"""
            ).fetchall()
            source_feedback = connection.execute(
                """SELECT COALESCE(d.source, '') AS source, f.type, COUNT(DISTINCT f.id) AS count
                FROM feedback f JOIN discoveries d ON d.opportunity_id = f.opportunity_id
                GROUP BY d.source, f.type"""
            ).fetchall()
        feedback_by_source: dict[str, dict[str, int]] = {}
        for row in source_feedback:
            feedback_by_source.setdefault(row["source"], {})[row["type"]] = row["count"]
        return {
            "schema_version": 1,
            "category": category,
            "profile": profile,
            "policy": {**policy, "category": policy.get("categories", {}).get(category, {})},
            "strategy": {"global": strategy.get("global", {}), "category": category_strategy},
            "recent_history": {
                "seen_urls": [row["canonical_url"] for row in seen],
                "recent_organizations": [row["organization"] for row in organizations],
                "recent_feedback_summary": {row["type"]: row["count"] for row in feedback_rows},
                "source_stats": [
                    {
                        "source": row["source"],
                        "runs": row["runs"],
                        "candidates": row["candidates"],
                        "new": row["new_count"] or 0,
                        "verified": row["verified"] or 0,
                        "useful": feedback_by_source.get(row["source"], {}).get("useful", 0),
                        "stale": feedback_by_source.get(row["source"], {}).get("stale", 0),
                        "rejected": row["rejected"] or 0,
                    }
                    for row in source_rows
                ],
            },
        }

    def strategy_show(self) -> dict[str, Any]:
        self.initialize()
        return read_yaml(self.paths.strategy)

    def strategy_history(self, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM strategy_revisions ORDER BY revision DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "revision": row["revision"],
                "created_at": row["created_at"],
                "reason": row["reason"],
                "evidence": _decode(row["evidence_json"], []),
                "diff": _decode(row["diff_json"], {}),
                "agent": row["agent"],
                "model": row["model"],
                "previous_revision": row["previous_revision"],
            }
            for row in rows
        ]

    def propose_strategy(self, value: dict[str, Any] | StrategyProposal) -> dict[str, Any]:
        self.initialize()
        proposal = (
            value if isinstance(value, StrategyProposal) else StrategyProposal.model_validate(value)
        )
        protected = {
            "profile",
            "policy",
            "privacy",
            "permissions",
            "output_security",
            "user_confirmation_requirements",
        }

        def find_protected(node: Any, path: str = "") -> str | None:
            if isinstance(node, dict):
                for key, child in node.items():
                    current = f"{path}.{key}" if path else key
                    if key.lower() in protected:
                        return current
                    found = find_protected(child, current)
                    if found:
                        return found
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    found = find_protected(child, f"{path}[{index}]")
                    if found:
                        return found
            return None

        protected_path = find_protected(proposal.changes)
        if protected_path:
            raise ValueError(f"Strategy proposal cannot mutate protected field: {protected_path}")
        if proposal.scope not in {"global", "*"} and not proposal.scope.strip():
            raise ValueError("Strategy proposal scope is required")

        current = self.strategy_show()
        current_revision = int(current.get("version", 1))
        updated = json.loads(_json(current))
        if proposal.scope in {"global", "*"}:
            target = dict(updated.get("global", {}))
            target = merge_mappings(target, proposal.changes)
            updated["global"] = target
        else:
            categories = dict(updated.get("categories", {}))
            categories[proposal.scope] = merge_mappings(
                dict(categories.get(proposal.scope, {})), proposal.changes
            )
            updated["categories"] = categories
        new_revision = current_revision + 1
        updated["version"] = new_revision
        created_at = proposal.created_at or utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO strategy_revisions
                (revision, created_at, reason, evidence_json, diff_json, agent,
                 model, previous_revision, strategy_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_revision,
                    created_at,
                    proposal.reason,
                    _json(proposal.evidence),
                    _json(proposal.changes),
                    proposal.proposed_by,
                    proposal.model,
                    current_revision,
                    _json(updated),
                ),
            )
        write_yaml(self.paths.strategy, updated)
        return {
            "schema_version": 1,
            "accepted": True,
            "revision": new_revision,
            "reason": proposal.reason,
            "strategy": updated,
        }

    def rollback_strategy(self, revision: int) -> dict[str, Any]:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM strategy_revisions WHERE revision = ?", (revision,)
            ).fetchone()
            latest = connection.execute(
                "SELECT MAX(revision) AS revision FROM strategy_revisions"
            ).fetchone()["revision"]
        if row is None:
            raise ValueError("Strategy revision not found")
        target = _decode(row["strategy_json"], {})
        new_revision = int(latest) + 1
        target["version"] = new_revision
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO strategy_revisions
                (revision, created_at, reason, evidence_json, diff_json, agent,
                 model, previous_revision, strategy_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_revision,
                    utc_now(),
                    f"rollback to revision {revision}",
                    _json([f"revision:{revision}"]),
                    _json({"rollback_to": revision}),
                    "operator",
                    None,
                    latest,
                    _json(target),
                ),
            )
        write_yaml(self.paths.strategy, target)
        return {
            "schema_version": 1,
            "revision": new_revision,
            "rolled_back_to": revision,
            "strategy": target,
        }
