"""Structured state-transition event collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agent.models import ProbeResult, ServiceState


@dataclass(frozen=True)
class StateChangeEvent:
    service: str
    previous_state: ServiceState
    current_state: ServiceState
    timestamp: datetime
    reason: str
    evidence: ProbeResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": "service_state_changed",
            "service": self.service,
            "previous_state": self.previous_state.value,
            "current_state": self.current_state.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
        }


class EventEmitter:
    def __init__(self) -> None:
        self.events: list[StateChangeEvent] = []

    def emit(self, event: StateChangeEvent) -> None:
        self.events.append(event)