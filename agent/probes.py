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
        self._owns_client = client is None

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
        if self.client is None:
            self.client = httpx.AsyncClient()
        health, ready = await asyncio.gather(
            self._get(self.client, f"{config.base_url}{config.healthz_path}"),
            self._get(self.client, f"{config.base_url}{config.readyz_path}"),
        )

        dependencies = _parse_dependencies(ready[1])
        errors = [message for message in (health[2], ready[2]) if message]
        return ProbeResult(
            service=config.name,
            timestamp=datetime.now(timezone.utc),
            healthz_status=health[0],
            readyz_status=ready[0],
            latency_ms=(time.perf_counter() - started) * 1000,
            dependencies=dependencies,
            resources=_parse_resources(ready[1]),
            pools=_parse_pools(ready[1]),
            error_reason="; ".join(errors) if errors else None,
        )

    async def aclose(self) -> None:
        if self._owns_client and self.client is not None:
            await self.client.aclose()
            self.client = None


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

def _safe_numbers(values, keys):
    import math
    if not isinstance(values, dict):
        return {}
    return {key: value for key,value in values.items() if key in keys
            and isinstance(value, (int,float)) and not isinstance(value,bool)
            and math.isfinite(value) and value >= 0}

def _parse_resources(body):
    if not isinstance(body, dict):
        return {}
    return _safe_numbers(body.get('resources'), {'memory_used_bytes','memory_limit_bytes',
        'memory_available_bytes','cpu_seconds','cpu_percent','process_cpu_seconds',
        'probe_cpu_seconds','probe_requests','monotonic_seconds'})

def _parse_pools(body):
    if not isinstance(body,dict) or not isinstance(body.get('checks'),dict):
        return {}
    result = {}
    for name in ('postgres','redis'):
        check = body['checks'].get(name, {})
        if isinstance(check,dict):
            result[name] = {'pool': _safe_numbers(check.get('pool'),
                {'max_connections','in_use','idle','waiting','available'}),
                'server_connections': _safe_numbers(check.get('server_connections'), {'used','capacity'})}
    return result
