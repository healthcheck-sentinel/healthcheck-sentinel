"""Control and report real healthcheck-sentinel demo conditions."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.classifier import classify
from agent.models import ServiceConfig, ServiceState
from agent.probes import ProbeRunner
from agent.registry import load_registry
from scripts.demo_states import write_lease
from scripts.local_action import require_local_engine

COMPOSE = ROOT / "docker-compose.yml"
STATUS_URL = os.getenv("DEMO_STATUS_URL", "http://127.0.0.1:9101/status")
CONTAINERS = ("postgres", "redis", "payment-service", "order-service", "user-service", "monitoring-agent")
APPLICATIONS = ("payment-service", "order-service", "user-service")
DIRECT_PROBE_TIMEOUT_SECONDS = 5.0
log = logging.getLogger("demo")


def monitor_snapshot() -> dict:
    with urlopen(STATUS_URL, timeout=5) as response:
        snapshot = json.load(response)
    if not isinstance(snapshot.get("services"), dict):
        raise RuntimeError("Monitoring agent has not published a service snapshot yet")
    return snapshot


async def probe_services(registry: tuple[ServiceConfig, ...] | None = None) -> tuple[dict[str, ServiceConfig], dict[str, dict]]:
    configs = registry or load_registry()
    runner = ProbeRunner(timeout_seconds=DIRECT_PROBE_TIMEOUT_SECONDS)
    try:
        results = await asyncio.gather(*(runner.probe(config) for config in configs))
    finally:
        await runner.aclose()
    config_map = {config.name: config for config in configs}
    return config_map, {
        result.service: {"evidence": result, "state": classify(config_map[result.service], result)[0]}
        for result in results
    }


def _dependency_cell(config: ServiceConfig, evidence, dependency: str) -> str:
    if evidence.healthz_status is None:
        return "-"
    if dependency in evidence.dependencies:
        return "OK" if evidence.dependencies[dependency] else "FAIL"
    return "UNKNOWN" if dependency in config.critical_dependencies else "N/A"


def print_table(configs: dict[str, ServiceConfig], observations: dict[str, dict]) -> None:
    print(f"{'SERVICE':<18} {'HEALTHZ':<12} {'READYZ':<7} {'POSTGRES':<10} {'REDIS':<8} STATE")
    for name in sorted(configs):
        config = configs[name]
        observation = observations[name]
        evidence = observation["evidence"]
        healthz = str(evidence.healthz_status) if evidence.healthz_status is not None else "UNREACHABLE"
        readyz = str(evidence.readyz_status) if evidence.readyz_status is not None else "-"
        print(
            f"{name:<18} {healthz:<12} {readyz:<7} "
            f"{_dependency_cell(config, evidence, 'postgres'):<10} "
            f"{_dependency_cell(config, evidence, 'redis'):<8} "
            f"{observation['state'].value}"
        )


def docker_container_health(container: str) -> str:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", container],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return "unavailable"
    status, _, health = result.stdout.strip().partition("|")
    if status != "running":
        return status or "unavailable"
    return health if health and health != "none" else status


def print_labeled_status(configs: dict[str, ServiceConfig], observations: dict[str, dict]) -> None:
    print("Docker Container Health (Docker only):")
    for container in CONTAINERS:
        print(f"{container}: {docker_container_health(container)}")
    print("HealthCheck Sentinel State (real probes and classifier):")
    print_table(configs, observations)


def dominant_state(observations: dict[str, dict]) -> ServiceState:
    priority = (ServiceState.DOWN, ServiceState.ZOMBIE, ServiceState.DEGRADED)
    for state in priority:
        if any(item["state"] == state for item in observations.values()):
            return state
    return ServiceState.HEALTHY


def print_reviewer_summary(scenario: str, configs: dict[str, ServiceConfig], observations: dict[str, dict],
                           snapshot: dict | None = None, incident: dict | None = None) -> None:
    print("\n=== REVIEWER SUMMARY ===")
    print(f"Scenario: {scenario}")
    state = dominant_state(observations)
    print(f"Sentinel classification: {state.value}")
    for name in ("payment-service", "order-service"):
        if name not in observations:
            continue
        evidence = observations[name]["evidence"]
        docker_health = docker_container_health(name)
        print(f"{name} Docker Container Health: {docker_health}")
        print(f"{name} Sentinel State: {observations[name]['state'].value}")
        print(f"{name} process alive: {'YES' if evidence.healthz_status is not None else 'NO'}")
        print(f"{name} /healthz: {evidence.healthz_status if evidence.healthz_status is not None else 'UNREACHABLE'}")
        print(f"{name} /readyz: {evidence.readyz_status if evidence.readyz_status is not None else '-'}")
        print(f"{name} PostgreSQL: {_dependency_cell(configs[name], evidence, 'postgres')}")
        print(f"{name} Redis: {_dependency_cell(configs[name], evidence, 'redis')}")
        if observations[name]["state"] == ServiceState.DEGRADED:
            print(f"Reason: {classify(configs[name], evidence)[1]}")
            print(f"Measured latency: {evidence.latency_ms:.2f} ms")
    if incident:
        cause = incident.get("root_cause", "unknown")
        cause_label = {"postgresql": "PostgreSQL", "response_latency": "High response latency"}.get(cause, cause)
        print(f"Root cause: {cause_label}")
        print(f"Affected services: {', '.join(incident.get('affected_services', []))}")
        print(f"Incident: {incident.get('incident_id', 'unknown')}")
        print(f"Detection time: {incident.get('detection_time_seconds', 'not tracked')} seconds")
        if snapshot:
            print(f"Slack: {delivery_result(snapshot, incident, 'ACTIVE')}")
    else:
        print("Incident: none")
        print("Slack: no transition")


def print_reasons(configs: dict[str, ServiceConfig], observations: dict[str, dict]) -> None:
    for name, observation in sorted(observations.items()):
        if observation["state"] != ServiceState.HEALTHY:
            evidence = observation["evidence"]
            _, reason = classify(configs[name], evidence)
            print(f"Reason ({name}): {reason}")
            if evidence.latency_ms:
                print(f"Measured latency ({name}): {evidence.latency_ms:.2f} ms")


def load_registry_map() -> dict[str, ServiceConfig]:
    return {config.name: config for config in load_registry()}


def print_incidents(snapshot: dict) -> None:
    active = [incident for incident in snapshot.get("incidents", []) if incident.get("status") == "ACTIVE"]
    if not active:
        print("Active incidents: none")
        return
    print("Active incidents:")
    for incident in active:
        print(
            f"{incident['incident_id']} {incident['state']} | "
            f"root cause: {incident['root_cause']} | "
            f"affected: {', '.join(incident['affected_services'])} | "
            f"Slack: {delivery_result(snapshot, incident, 'ACTIVE')}"
        )


def delivery_result(snapshot: dict, incident: dict, event: str) -> str:
    deliveries = snapshot.get("notifications", [])
    match = next(
        (
            item for item in reversed(deliveries)
            if item.get("incident_id") == incident.get("incident_id") and item.get("status") == event
        ),
        None,
    )
    return match.get("outcome", "pending") if match else "not recorded"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def incident_duration(incident: dict) -> float | None:
    started = _parse_time(incident.get("first_failure_time"))
    recovered = _parse_time(incident.get("recovery_time"))
    if started is None or recovered is None:
        return None
    return round(max(0.0, (recovered - started).total_seconds()), 2)


def _fresh(snapshot: dict, after: datetime) -> bool:
    observed = _parse_time(snapshot.get("observed_at"))
    return observed is not None and observed >= after


def wait_for_agent(expected: dict[str, str], after: datetime, timeout: float = 35) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            snapshot = monitor_snapshot()
            if _fresh(snapshot, after) and all(
                snapshot["services"].get(name, {}).get("state") == state
                for name, state in expected.items()
            ):
                return snapshot
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            last_error = exc
        time.sleep(0.5)
    details = f" ({last_error})" if last_error else ""
    raise TimeoutError(f"Monitoring agent did not confirm {expected} within {timeout:g}s{details}")


def compose(*args: str, timeout: int = 60, demo_enabled: bool = False) -> None:
    environment = os.environ.copy()
    if demo_enabled:
        environment['SENTINEL_DEMO_ENABLED'] = '1'
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), *args],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def ensure_running(container: str) -> None:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0 or result.stdout.strip().lower() != "true":
        compose("up", "-d", "--no-deps", container, timeout=120)


def wait_container_healthy(container: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", container],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip().lower() == "healthy":
            return
        time.sleep(1)
    raise TimeoutError(f"Docker health did not become healthy for {container}")


def ensure_required_containers() -> None:
    require_local_engine()
    for container in CONTAINERS:
        ensure_running(container)
    for container in CONTAINERS:
        wait_container_healthy(container)


def wait_for_real_healthy(timeout: float = 120) -> tuple[dict[str, ServiceConfig], dict[str, dict]]:
    deadline = time.monotonic() + timeout
    configs = load_registry_map()
    last: tuple[dict[str, ServiceConfig], dict[str, dict]] | None = None
    while time.monotonic() < deadline:
        last = asyncio.run(probe_services(tuple(configs.values())))
        if all(item["state"] == ServiceState.HEALTHY for item in last[1].values()):
            return last
        time.sleep(1)
    if last:
        print_table(*last)
    raise TimeoutError("Real health, readiness, and dependency checks did not all pass")


def require_confirmed_healthy(timeout: float = 35) -> None:
    configs, observations = asyncio.run(probe_services())
    if any(item["state"] != ServiceState.HEALTHY for item in observations.values()):
        print_table(configs, observations)
        raise RuntimeError("Restore the actual services with 'python demo.py recover' before injecting another failure")
    snapshot = monitor_snapshot()
    if any(snapshot["services"].get(name, {}).get("state") != "HEALTHY" for name in configs):
        raise RuntimeError("Waiting for monitoring-agent to confirm HEALTHY before injecting a condition")


def active_incidents(snapshot: dict) -> list[dict]:
    return [incident for incident in snapshot.get("incidents", []) if incident.get("status") == "ACTIVE"]


def print_transition_incident(snapshot: dict, state: str, services: set[str]) -> None:
    candidates = [
        incident for incident in active_incidents(snapshot)
        if incident.get("state") == state and services.intersection(incident.get("affected_services", []))
    ]
    for incident in candidates:
        print(f"Incident ID: {incident['incident_id']}")
        root_cause = incident.get("root_cause", "unknown")
        cause_label = {"postgresql": "PostgreSQL", "response_latency": "High response latency"}.get(root_cause, root_cause)
        print(f"Root Cause: {cause_label}")
        print(f"First failure observed: {incident.get('first_failure_time', 'n/a')}")
        print(f"Confirmation time: {incident.get('confirmation_time', 'n/a')}")
        detection_time = incident.get("detection_time_seconds")
        if detection_time is None and state == "DEGRADED":
            print("Measured detection time: not recorded")
        else:
            print(f"Measured detection time: {detection_time} seconds")
        print(f"Affected services: {', '.join(incident.get('affected_services', []))}")
        print(f"Slack delivery: {delivery_result(snapshot, incident, 'ACTIVE')}")


def command_healthy() -> int:
    ensure_required_containers()
    configs, observations = asyncio.run(probe_services())
    print_labeled_status(configs, observations)
    print_reasons(configs, observations)
    print_reviewer_summary("HEALTHY" if dominant_state(observations) == ServiceState.HEALTHY else "REAL CURRENT STATE", configs, observations)
    return 0 if all(item["state"] == ServiceState.HEALTHY for item in observations.values()) else 1


def command_status() -> int:
    configs, observations = asyncio.run(probe_services())
    print_labeled_status(configs, observations)
    snapshot = None
    try:
        snapshot = monitor_snapshot()
        print_incidents(snapshot)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Incident snapshot unavailable: {type(exc).__name__}")
    active = active_incidents(snapshot or {})
    print("\n=== REVIEWER SUMMARY ===")
    print("Scenario: STATUS (read-only)")
    print(f"Sentinel classification: {dominant_state(observations).value}")
    print(f"Active incidents: {len(active)}")
    return 0


def command_degraded() -> int:
    require_local_engine()
    ensure_required_containers()
    require_confirmed_healthy()
    # Explicit invocation enables only payment's bounded latency middleware.
    # No secret or flag is written to .env; ordinary Compose defaults remain off.
    compose('up', '-d', '--no-deps', 'payment-service', timeout=120, demo_enabled=True)
    wait_container_healthy('payment-service')
    wait_for_real_healthy()
    wait_for_agent({name: 'HEALTHY' for name in load_registry_map()}, datetime.now(timezone.utc))
    started = datetime.now(timezone.utc)
    write_lease("degraded", seconds=45, latency_ms=2000)
    snapshot = wait_for_agent({"payment-service": "DEGRADED"}, started)
    configs, observations = asyncio.run(probe_services())
    if observations["payment-service"]["state"] != ServiceState.DEGRADED:
        raise RuntimeError("The agent confirmed DEGRADED, but a fresh real probe no longer supports it")
    print_labeled_status(configs, observations)
    print_reasons(configs, observations)
    print_transition_incident(snapshot, "DEGRADED", {"payment-service"})
    incident = next((item for item in active_incidents(snapshot) if item.get("state") == "DEGRADED" and "payment-service" in item.get("affected_services", [])), None)
    if incident is None:
        raise RuntimeError("Confirmed DEGRADED state has no active correlated incident")
    print_reviewer_summary("DEGRADED", configs, observations, snapshot, incident)
    return 0


def command_zombie() -> int:
    require_local_engine()
    ensure_required_containers()
    require_confirmed_healthy()
    write_lease("healthy")
    started = datetime.now(timezone.utc)
    compose("stop", "--timeout", "1", "postgres", timeout=20)
    snapshot = wait_for_agent({"payment-service": "ZOMBIE", "order-service": "ZOMBIE"}, started)
    configs, observations = asyncio.run(probe_services())
    if any(observations[name]["state"] != ServiceState.ZOMBIE for name in ("payment-service", "order-service")):
        raise RuntimeError("The agent confirmed ZOMBIE, but fresh real probes do not support the classification")
    print_labeled_status(configs, observations)
    print_transition_incident(snapshot, "ZOMBIE", {"payment-service", "order-service"})
    incident = next((item for item in active_incidents(snapshot) if item.get("state") == "ZOMBIE" and {"payment-service", "order-service"}.issubset(set(item.get("affected_services", [])))), None)
    if incident is None:
        raise RuntimeError("Confirmed shared ZOMBIE states have no single correlated incident")
    print_reviewer_summary("ZOMBIE", configs, observations, snapshot, incident)
    return 0


def command_down() -> int:
    require_local_engine()
    ensure_required_containers()
    require_confirmed_healthy()
    started = datetime.now(timezone.utc)
    compose("stop", "--timeout", "1", "payment-service", timeout=20)
    snapshot = wait_for_agent({"payment-service": "DOWN"}, started, timeout=40)
    configs, observations = asyncio.run(probe_services())
    if observations["payment-service"]["state"] != ServiceState.DOWN:
        raise RuntimeError("The agent confirmed DOWN, but a fresh /healthz probe no longer supports it")
    print_labeled_status(configs, observations)
    print_transition_incident(snapshot, "DOWN", {"payment-service"})
    incident = next((item for item in active_incidents(snapshot) if item.get("state") == "DOWN" and "payment-service" in item.get("affected_services", [])), None)
    if incident is None:
        raise RuntimeError("Confirmed DOWN state has no active correlated incident")
    print_reviewer_summary("DOWN", configs, observations, snapshot, incident)
    return 0


def command_recover() -> int:
    require_local_engine()
    before = monitor_snapshot()
    previous_incidents = active_incidents(before)
    previous_state = previous_incidents[0].get("state", "HEALTHY") if previous_incidents else "HEALTHY"
    write_lease("healthy")
    for container in CONTAINERS:
        ensure_running(container)
    for container in CONTAINERS:
        wait_container_healthy(container)
    configs, observations = wait_for_real_healthy()
    after = wait_for_agent({name: ServiceState.HEALTHY.value for name in configs}, datetime.now(timezone.utc), timeout=40)
    if previous_incidents:
        resolved = {
            incident.get("incident_id"): incident
            for incident in after.get("incidents", [])
            if incident.get("status") == "RESOLVED"
        }
        for incident in previous_incidents:
            resolved_incident = resolved.get(incident.get("incident_id"))
            if not resolved_incident:
                continue
            print("\nSERVICE RECOVERED")
            print(f"Incident ID: {resolved_incident['incident_id']}")
            affected = resolved_incident.get("affected_services", [])
            print(f"Service: {', '.join(affected)}")
            print(f"Previous State: {resolved_incident.get('state')}")
            current_state = observations[affected[0]]["state"].value if affected else "UNKNOWN"
            print(f"Current State: {current_state}")
            cause = resolved_incident.get("root_cause", "unknown")
            cause_label = {"postgresql": "PostgreSQL", "response_latency": "High response latency"}.get(cause, cause)
            print(f"Root Cause: {cause_label}")
            print(f"Recovery time: {resolved_incident.get('recovery_time', 'n/a')}")
            duration = incident_duration(resolved_incident)
            print(f"Incident duration: {duration if duration is not None else 'n/a'} seconds")
            print(f"Slack recovery delivery: {delivery_result(after, resolved_incident, 'RESOLVED')}")
        resolved_ids = {item.get("incident_id") for item in resolved.values()}
        missing = [item.get("incident_id") for item in previous_incidents if item.get("incident_id") not in resolved_ids]
        if missing:
            raise RuntimeError(f"Agent has not resolved active incidents: {', '.join(missing)}")
    print_labeled_status(configs, observations)
    print("\n=== REVIEWER SUMMARY ===")
    print(f"Previous state: {previous_state}")
    print(f"Current state: {dominant_state(observations).value}")
    print(f"Incident: {', '.join(item.get('incident_id', 'unknown') for item in previous_incidents) if previous_incidents else 'none (idempotent recovery)'}")
    if previous_incidents:
        durations = [incident_duration(item) for item in after.get("incidents", []) if item.get("incident_id") in {active.get("incident_id") for active in previous_incidents}]
        print(f"Incident duration: {', '.join(str(value) for value in durations if value is not None) or 'pending'} seconds")
        recovery_statuses = [delivery_result(after, item, "RESOLVED") for item in after.get("incidents", []) if item.get("incident_id") in {active.get("incident_id") for active in previous_incidents}]
        print(f"Slack recovery: {', '.join(recovery_statuses) or 'not recorded'}")
    else:
        print("Incident duration: n/a")
        print("Slack recovery: no transition")
    return 0


COMMANDS = {
    "healthy": command_healthy,
    "degraded": command_degraded,
    "zombie": command_zombie,
    "down": command_down,
    "recover": command_recover,
    "status": command_status,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=tuple(COMMANDS))
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        return COMMANDS[args.command]()
    except KeyboardInterrupt:
        log.warning("Interrupted. Use 'python demo.py recover' to restore real services.")
        return 130
    except (OSError, ValueError, KeyError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        log.error("Demo command failed (%s). Check Docker and run the recover command.", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())