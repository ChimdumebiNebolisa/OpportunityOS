"""Stable opportunity identity helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "referrer",
}


def normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are supported")
    host = parts.hostname.lower()
    if parts.port:
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/") or "/"
    query = sorted(
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith("utm_")
    )
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def _clean(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def fingerprint(
    organization: str,
    title: str,
    category: str,
    metadata: dict[str, object] | None = None,
) -> str:
    metadata = metadata or {}
    cycle = metadata.get("cycle") or metadata.get("year") or metadata.get("season") or ""
    raw = "|".join((_clean(organization), _clean(title), _clean(category), _clean(cycle)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
