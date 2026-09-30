from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Incident:
    incident_id: str
    status: str
    state: str
    root_cause: str
    affected_services: list[str] = field(default_factory=list)
    first_failure_time: str | None = None
    confirmation_time: str | None = None
    recovery_time: str | None = None
    detection_time_seconds: float | None = None
    explanation: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Incident":
        return cls(
            incident_id=str(data.get("incident_id", "UNKNOWN")),
            status=str(data.get("status", "ACTIVE")).upper(),
            state=str(data.get("state", "UNKNOWN")).upper(),
            root_cause=str(data.get("root_cause", "unknown")),
            affected_services=list(data.get("affected_services") or []),
            first_failure_time=data.get("first_failure_time"),
            confirmation_time=data.get("confirmation_time"),
            recovery_time=data.get("recovery_time"),
            detection_time_seconds=data.get("detection_time_seconds"),
            explanation=str(data.get("explanation") or ""),
            evidence=dict(data.get("evidence") or {}),
        )

    @property
    def is_resolved(self) -> bool:
        return self.status.upper() == "RESOLVED"
