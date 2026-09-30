"""Opt-in, expiring latency injection for real payment probe responses."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
import time


class DemoLatency:
    def __init__(self, app, lease_path: str, enabled: bool = False):
        self.app = app
        self.lease_path = Path(lease_path)
        self.enabled = enabled

    def delay_seconds(self) -> float:
        if not self.enabled:
            return 0
        try:
            lease = json.loads(self.lease_path.read_text(encoding="utf-8"))
            issued_at = lease["issued_at"]
            expires_at = lease["expires_at"]
            latency_ms = lease["latency_ms"]
            if not (0 < expires_at - issued_at <= 60 and issued_at <= time.time() < expires_at):
                return 0
            if lease["mode"] != "degraded":
                return 0
            if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)):
                return 0
            if not math.isfinite(latency_ms) or not 500 <= latency_ms <= 5000:
                return 0
            return latency_ms / 1000
        except (OSError, ValueError, KeyError, TypeError):
            return 0

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") in ("/healthz", "/readyz"):
            delay = self.delay_seconds()
            if delay:
                await asyncio.sleep(delay)
        await self.app(scope, receive, send)