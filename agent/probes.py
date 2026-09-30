"""Asynchronous HTTP probes for registered services."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from agent.models import ProbeResult, ServiceConfig


class ProbeRunner:
    def __init__(self, timeout_seconds: float = 3.0, client: httpx.AsyncClient | None = None):
        self.timeout_seconds = timeout_seconds
        self.client = client

    async def _get(self, client: httpx.AsyncClient, url: str) -> tuple[int | None, Any, str | None]:
        try:
            response = await client.get(url, timeout=self.timeout_seconds)
            try:
                body = response.json()
            except ValueError:
                body = None
            error = None if response.is_success else f"HTTP {response.status_code} from {url}"
            return response.status_code, body, error
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            return None, None, f"{type(exc).__name__}: {exc}"

    async def probe(self, config: ServiceConfig) -> ProbeResult:
        started = time.perf_counter()
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient()
        try:
            health, ready = await asyncio.gather(
                self._get(client, f"{config.base_url}{config.healthz_path}"),
                self._get(client, f"{config.base_url}{config.readyz_path}"),
            )
        finally:
            if owns_client:
                await client.aclose()

        dependencies = _parse_dependencies(ready[1])
        errors = [message for message in (health[2], ready[2]) if message]
        return ProbeResult(
            service=config.name,
            timestamp=datetime.now(timezone.utc),
            healthz_status=health[0],
            readyz_status=ready[0],
            latency_ms=(time.perf_counter() - started) * 1000,
            dependencies=dependencies,
            error_reason="; ".join(errors) if errors else None,
        )


def _parse_dependencies(body: Any) -> dict[str, bool]:
    if not isinstance(body, dict):
        return {}
    checks = body.get("checks")
    if not isinstance(checks, dict):
        return {}
    results: dict[str, bool] = {}
    for name, detail in checks.items():
        if isinstance(detail, dict) and isinstance(detail.get("ok"), bool):
            results[name] = detail["ok"]
        elif isinstance(detail, bool):
            results[name] = detail
    return results