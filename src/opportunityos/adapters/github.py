"""Conservative GitHub metadata adapter; code contents are out of v1 scope."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx


class GitHubAuthRequiredError(ValueError):
    """Raised when GitHub credentials are absent or expired for the requested metadata."""


@dataclass(frozen=True)
class GitHubEvidence:
    field_path: str
    value: Any
    evidence_url: str
    assertion_kind: str = "observed"


class GitHubClient:
    def __init__(self, token: str | None = None, client: httpx.Client | None = None) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "OpportunityOS/1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(
            base_url="https://api.github.com", timeout=15, headers=headers
        )

    def repository_evidence(self, username: str) -> list[GitHubEvidence]:
        response = self.client.get(
            f"/users/{username}/repos", params={"per_page": 100, "sort": "updated"}
        )
        if response.status_code == 401:
            raise GitHubAuthRequiredError(
                "GitHub authentication expired; run `gh auth login` or update the private token"
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("GitHub returned an unexpected repository payload")
        evidence: list[GitHubEvidence] = []
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            url = str(item.get("html_url", ""))
            prefix = f"github.repositories.{name}"
            evidence.extend(
                [
                    GitHubEvidence(f"{prefix}.exists", True, url),
                    GitHubEvidence(f"{prefix}.url", url, url),
                    GitHubEvidence(f"{prefix}.description", item.get("description"), url),
                    GitHubEvidence(f"{prefix}.language", item.get("language"), url),
                    GitHubEvidence(f"{prefix}.topics", item.get("topics", []), url),
                    GitHubEvidence(f"{prefix}.archived", bool(item.get("archived")), url),
                    GitHubEvidence(f"{prefix}.private", bool(item.get("private")), url),
                    GitHubEvidence(f"{prefix}.updated_at", item.get("updated_at"), url),
                ]
            )
        for item in payload[:10]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            repository_name = item["name"]
            release_response = self.client.get(
                f"/repos/{username}/{repository_name}/releases", params={"per_page": 10}
            )
            if release_response.status_code == 401:
                raise GitHubAuthRequiredError(
                    "GitHub authentication expired; run `gh auth login` or update the private token"
                )
            release_response.raise_for_status()
            release_payload = release_response.json()
            if not isinstance(release_payload, list):
                raise ValueError("GitHub returned an unexpected releases payload")
            for release in release_payload[:10]:
                if not isinstance(release, dict) or not isinstance(release.get("tag_name"), str):
                    continue
                tag = re.sub(r"[^A-Za-z0-9_.-]", "_", release["tag_name"])[:100]
                url = str(release.get("html_url", ""))
                prefix = f"github.repositories.{repository_name}.releases.{tag}"
                evidence.extend(
                    [
                        GitHubEvidence(f"{prefix}.exists", True, url),
                        GitHubEvidence(f"{prefix}.url", url, url),
                        GitHubEvidence(f"{prefix}.name", release.get("name"), url),
                        GitHubEvidence(f"{prefix}.published_at", release.get("published_at"), url),
                        GitHubEvidence(
                            f"{prefix}.prerelease", bool(release.get("prerelease")), url
                        ),
                    ]
                )
        merged_response = self.client.get(
            "/search/issues",
            params={
                "q": f"author:{username} is:pr is:merged",
                "per_page": 100,
                "sort": "updated",
            },
        )
        if merged_response.status_code == 401:
            raise GitHubAuthRequiredError(
                "GitHub authentication expired; run `gh auth login` or update the private token"
            )
        merged_response.raise_for_status()
        merged_payload = merged_response.json()
        if not isinstance(merged_payload, dict) or not isinstance(
            merged_payload.get("items"), list
        ):
            raise ValueError("GitHub returned an unexpected merged pull-request payload")
        for item in merged_payload["items"][:100]:
            if not isinstance(item, dict) or not isinstance(item.get("number"), int):
                continue
            repository_name = str(item.get("repository_url", "")).rstrip("/").rsplit("/", 1)[-1]
            if not repository_name:
                continue
            number = int(item["number"])
            url = str(item.get("html_url", ""))
            prefix = f"github.merged_pull_requests.{repository_name}.{number}"
            evidence.extend(
                [
                    GitHubEvidence(f"{prefix}.exists", True, url),
                    GitHubEvidence(f"{prefix}.url", url, url),
                    GitHubEvidence(f"{prefix}.title", item.get("title"), url),
                    GitHubEvidence(f"{prefix}.repository", repository_name, url),
                    GitHubEvidence(f"{prefix}.merged_at", item.get("closed_at"), url),
                ]
            )
        return evidence
