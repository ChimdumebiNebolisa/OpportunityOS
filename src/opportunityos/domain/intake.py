"""Pure normalization, deduplication, and source-safety helpers."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are supported")
    host = parts.hostname.lower()
    port = f":{parts.port}" if parts.port else ""
    path = parts.path.rstrip("/") or "/"
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith("utm_")
    ]
    return urlunsplit((parts.scheme.lower(), f"{host}{port}", path, urlencode(query), ""))


def semantic_key(organization: str, title: str, cycle: str | None) -> tuple[str, str]:
    def clean(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    family = f"{clean(organization)}|{clean(title)}"
    return family, f"{family}|{clean(cycle or 'uncycled')}"


INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"(reveal|print|upload|read)\s+.*(secret|token|environment|local file)", re.I),
    re.compile(r"run\s+(a\s+)?(shell|terminal|command)", re.I),
    re.compile(r"mark\s+.*eligible", re.I),
)


def detect_prompt_injection(text: str) -> list[str]:
    return [pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(text)]
