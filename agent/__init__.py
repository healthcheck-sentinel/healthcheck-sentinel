"""
agent package — HealthCheck Sentinel monitoring agent

This is a deterministic, rule-based monitoring agent. It contains no LLM or
generative AI. All decisions are made by explicit logic and configurable thresholds.

Responsibilities:
  - Poll service health endpoints (/healthz, /readyz) on a defined schedule
  - Track state transitions (healthy → degraded → unhealthy → recovering)
  - Apply configurable threshold rules (e.g. N consecutive failures = alert)
  - Emit structured events for downstream consumers (alert_manager, chatops)
  - Maintain a rolling window of check results for trend detection

What this agent does NOT do:
  - No LLM inference
  - No generative AI
  - No probabilistic or ML-based decisions
  - No external AI API calls

Design principles:
  - Deterministic: the same inputs always produce the same outputs
  - Transparent: every decision is traceable to a specific rule and threshold
  - Fast: polling and evaluation are non-blocking async operations
  - Self-contained: the agent can run without any external AI service
"""

from agent.dependency_graph import DependencyGraph, normalize_dependency_name
from agent.incidents import Incident, IncidentManager
from agent.models import ProbeResult, ServiceConfig, ServiceState, ServiceStatus
from agent.root_cause import CorrelatedFailure, RootCauseAnalyzer

__all__ = [
    "DependencyGraph",
    "normalize_dependency_name",
    "Incident",
    "IncidentManager",
    "ProbeResult",
    "ServiceConfig",
    "ServiceState",
    "ServiceStatus",
    "CorrelatedFailure",
    "RootCauseAnalyzer",
]
