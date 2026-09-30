from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import demo
import reviewer_demo
from agent.models import ProbeResult, ServiceConfig, ServiceState


def observation(config: ServiceConfig, state: ServiceState) -> dict:
    return {
        "evidence": ProbeResult(
            service=config.name,
            timestamp=datetime.now(timezone.utc),
            healthz_status=200 if state != ServiceState.DOWN else None,
            readyz_status=200 if state == ServiceState.HEALTHY else 503,
            latency_ms=20.0,
            dependencies={"postgres": True, "redis": True},
        ),
        "state": state,
    }


def test_status_probes_without_mutating_demo_or_compose(monkeypatch, capsys) -> None:
    config = ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis"))

    async def probes():
        return {config.name: config}, {config.name: observation(config, ServiceState.HEALTHY)}

    monkeypatch.setattr(demo, "probe_services", probes)
    monkeypatch.setattr(demo, "monitor_snapshot", lambda: {
        "services": {},
        "incidents": [{"incident_id": "INC-001", "status": "ACTIVE", "state": "DEGRADED", "root_cause": "response_latency", "affected_services": [config.name]}],
        "notifications": [{"incident_id": "INC-001", "status": "ACTIVE", "outcome": "delivered"}],
    })
    monkeypatch.setattr(demo, "docker_container_health", lambda _name: "healthy")
    monkeypatch.setattr(demo, "write_lease", lambda *args, **kwargs: pytest.fail("status wrote a latency lease"))
    monkeypatch.setattr(demo, "compose", lambda *args, **kwargs: pytest.fail("status changed Docker"))
    monkeypatch.setattr(demo, "ensure_running", lambda *args, **kwargs: pytest.fail("status started a service"))

    assert demo.command_status() == 0
    output = capsys.readouterr().out
    assert "payment-service" in output
    assert "Docker Container Health" in output
    assert "HealthCheck Sentinel State" in output
    assert "INC-001 DEGRADED" in output
    assert "Slack: delivered" in output
    assert "Reason (payment-service)" not in output


def test_healthy_ensures_containers_and_reports_real_degraded_probe(monkeypatch, capsys):
    config = ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis"))
    monkeypatch.setattr(demo, "ensure_required_containers", lambda: None)

    async def probes():
        return {config.name: config}, {config.name: observation(config, ServiceState.DEGRADED)}

    monkeypatch.setattr(demo, "probe_services", probes)
    monkeypatch.setattr(demo, "docker_container_health", lambda _name: "healthy")
    monkeypatch.setattr(demo, "write_lease", lambda *_args, **_kwargs: pytest.fail("healthy injected a demo condition"))

    assert demo.command_healthy() == 1
    output = capsys.readouterr().out
    assert "Sentinel classification: DEGRADED" in output
    assert "Docker Container Health" in output


def test_incident_duration_uses_recorded_times() -> None:
    assert demo.incident_duration({
        "first_failure_time": "2026-09-30T12:00:00+00:00",
        "recovery_time": "2026-09-30T12:00:12.345000+00:00",
    }) == 12.35


def test_recovery_waits_for_live_readiness_before_returning(monkeypatch) -> None:
    config = ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis"))
    samples = [
        ({config.name: config}, {config.name: observation(config, ServiceState.ZOMBIE)}),
        ({config.name: config}, {config.name: observation(config, ServiceState.DEGRADED)}),
        ({config.name: config}, {config.name: observation(config, ServiceState.HEALTHY)}),
    ]
    calls = 0

    async def probes(_registry=None):
        nonlocal calls
        sample = samples[min(calls, len(samples) - 1)]
        calls += 1
        return sample

    monkeypatch.setattr(demo, "probe_services", probes)
    monkeypatch.setattr(demo.time, "sleep", lambda _seconds: None)

    configs, observations = demo.wait_for_real_healthy(timeout=1)

    assert calls == 3
    assert configs[config.name] == config
    assert observations[config.name]["state"] == ServiceState.HEALTHY


def test_recovery_does_not_return_healthy_when_readiness_never_passes(monkeypatch) -> None:
    config = ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis"))

    async def probes(_registry=None):
        return {config.name: config}, {config.name: observation(config, ServiceState.ZOMBIE)}

    monkeypatch.setattr(demo, "probe_services", probes)
    clock = SimpleNamespace(monotonic=iter([0.0, 0.0, 2.0]).__next__, sleep=lambda _seconds: None)
    monkeypatch.setattr(demo, "time", clock)

    with pytest.raises(TimeoutError, match="Real health, readiness, and dependency checks"):
        demo.wait_for_real_healthy(timeout=1)


@pytest.mark.parametrize("previous_state", ["DEGRADED", "ZOMBIE", "DOWN"])
def test_reviewer_recovery_resolves_each_incident_state(monkeypatch, capsys, previous_state):
    config = ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis"))
    incident = {
        "incident_id": "INC-009",
        "status": "ACTIVE",
        "state": previous_state,
        "root_cause": "response_latency" if previous_state == "DEGRADED" else "postgresql",
        "affected_services": ["payment-service"],
        "first_failure_time": "2026-09-30T12:00:00+00:00",
        "confirmation_time": "2026-09-30T12:00:02+00:00",
    }
    resolved = {**incident, "status": "RESOLVED", "recovery_time": "2026-09-30T12:00:12+00:00"}
    before = {"services": {}, "incidents": [incident], "notifications": []}
    after = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "services": {config.name: {"state": "HEALTHY"}},
        "incidents": [resolved],
        "notifications": [{"incident_id": "INC-009", "status": "RESOLVED", "outcome": "delivered"}],
    }
    healthy = {config.name: observation(config, ServiceState.HEALTHY)}
    monkeypatch.setattr(demo, "require_local_engine", lambda: None)
    monkeypatch.setattr(demo, "monitor_snapshot", lambda: before)
    monkeypatch.setattr(demo, "active_incidents", lambda snapshot: snapshot["incidents"] if snapshot is before else [])
    monkeypatch.setattr(demo, "write_lease", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(demo, "ensure_running", lambda _container: None)
    monkeypatch.setattr(demo, "wait_container_healthy", lambda _container: None)
    monkeypatch.setattr(demo, "wait_for_real_healthy", lambda: ({config.name: config}, healthy))
    monkeypatch.setattr(demo, "wait_for_agent", lambda *_args, **_kwargs: after)
    monkeypatch.setattr(demo, "docker_container_health", lambda _name: "healthy")

    assert demo.command_recover() == 0
    output = capsys.readouterr().out
    assert f"Previous State: {previous_state}" in output
    assert "Current State: HEALTHY" in output
    assert "Incident duration: 12.0 seconds" in output
    assert "Slack recovery delivery: delivered" in output


def test_repeated_recover_is_idempotent(monkeypatch, capsys):
    config = ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis"))
    healthy = {config.name: observation(config, ServiceState.HEALTHY)}
    monkeypatch.setattr(demo, "require_local_engine", lambda: None)
    monkeypatch.setattr(demo, "monitor_snapshot", lambda: {"services": {}, "incidents": [], "notifications": []})
    monkeypatch.setattr(demo, "write_lease", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(demo, "ensure_running", lambda _container: None)
    monkeypatch.setattr(demo, "wait_container_healthy", lambda _container: None)
    monkeypatch.setattr(demo, "wait_for_real_healthy", lambda: ({config.name: config}, healthy))
    monkeypatch.setattr(demo, "wait_for_agent", lambda *_args, **_kwargs: {"incidents": []})
    monkeypatch.setattr(demo, "docker_container_health", lambda _name: "healthy")

    assert demo.command_recover() == 0
    assert demo.command_recover() == 0
    assert capsys.readouterr().out.count("Slack recovery: no transition") == 2


def test_reviewer_cli_exposes_only_six_requested_commands(capsys):
    with pytest.raises(SystemExit) as result:
        reviewer_demo.main(["--help"])
    assert result.value.code == 0
    output = capsys.readouterr().out
    for command in ("healthy", "degraded", "zombie", "down", "recover", "status"):
        assert command in output