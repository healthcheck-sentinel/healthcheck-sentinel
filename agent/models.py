"""Shared models for the deterministic monitoring agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class ServiceState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    ZOMBIE = "ZOMBIE"
    DOWN = "DOWN"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    base_url: str
    healthz_path: str = "/healthz"
    readyz_path: str = "/readyz"
    critical_dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProbeResult:
    service: str
    timestamp: datetime
    healthz_status: int | None
    readyz_status: int | None
    latency_ms: float
    dependencies: dict[str, bool] = field(default_factory=dict)
    error_reason: str | None = None
    resources: dict[str, Any] = field(default_factory=dict)
    pools: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "timestamp": self.timestamp.isoformat(),
            "healthz_status": self.healthz_status,
            "readyz_status": self.readyz_status,
            "latency_ms": round(self.latency_ms, 2),
            "dependencies": self.dependencies.copy(),
            "error_reason": self.error_reason,
            "resources": self.resources.copy(),
            "pools": self.pools.copy(),
        }


@dataclass
class ServiceStatus:
    service: str
    state: ServiceState = ServiceState.HEALTHY
    evidence: ProbeResult | None = None
    reason: str = "No probe has been recorded."
    first_failure_observed: datetime | None = None
    failure_confirmed_at: datetime | None = None
    recovery_first_observed: datetime | None = None
    recovery_confirmed_at: datetime | None = None
    detection_time_seconds: float | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "state": self.state.value,
            "reason": self.reason,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "first_failure_observed": _iso(self.first_failure_observed),
            "failure_confirmed_at": _iso(self.failure_confirmed_at),
            "recovery_first_observed": _iso(self.recovery_first_observed),
            "recovery_confirmed_at": _iso(self.recovery_confirmed_at),
            "detection_time_seconds": self.detection_time_seconds,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None