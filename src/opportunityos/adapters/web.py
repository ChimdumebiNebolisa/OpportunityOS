"""Bounded HTTP retrieval with SSRF and prompt-injection isolation."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from opportunityos.config.settings import Settings
from opportunityos.domain.intake import detect_prompt_injection, normalize_url


@dataclass(frozen=True)
class WebDocument:
    original_url: str
    final_url: str
    mime_type: str
    text: str
    content: bytes
    injection_signals: tuple[str, ...]


def system_resolver(host: str) -> list[str]:
    return list({str(item[4][0]) for item in socket.getaddrinfo(host, None)})


class SafeWebRetriever:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        resolver: Callable[[str], list[str]] = system_resolver,
    ) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            timeout=settings.web_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "OpportunityOS/1.0 (+local evidence verifier)"},
        )
        self.resolver = resolver

    def _validate_destination(self, url: str) -> str:
        normalized = normalize_url(url)
        host = urlsplit(normalized).hostname
        assert host is not None
        if host.lower() in {"localhost", "localhost.localdomain"}:
            raise ValueError("Local and private network destinations are not allowed")
        addresses = self.resolver(host)
        if not addresses:
            raise ValueError("Destination did not resolve")
        for address in addresses:
            parsed = ipaddress.ip_address(address)
            if not parsed.is_global:
                raise ValueError("Local and private network destinations are not allowed")
        return normalized

    def retrieve(self, url: str) -> WebDocument:
        original = self._validate_destination(url)
        current = original
        for _ in range(6):
            with self.client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response omitted a destination")
                    current = self._validate_destination(urljoin(current, location))
                    continue
                response.raise_for_status()
                mime = response.headers.get("content-type", "application/octet-stream").split(";")[
                    0
                ]
                if mime not in {"text/html", "text/plain", "application/xhtml+xml"}:
                    raise ValueError("Unsupported web content type")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.settings.max_web_bytes:
                        raise ValueError("Web response exceeds the configured size limit")
                content = bytes(body)
                decoded = content.decode(response.encoding or "utf-8", errors="replace")
                text = trafilatura.extract(decoded, include_links=True) or decoded
                if len(text) > 1_000_000:
                    text = text[:1_000_000]
                return WebDocument(
                    original_url=original,
                    final_url=normalize_url(str(response.url)),
                    mime_type=mime,
                    text=text,
                    content=content,
                    injection_signals=tuple(detect_prompt_injection(text)),
                )
        raise ValueError("Too many redirects")
