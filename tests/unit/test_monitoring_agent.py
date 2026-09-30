from datetime import datetime, timedelta, timezone

import httpx
import pytest

from agent.classifier import classify
from agent.events import EventEmitter
from agent.models import ProbeResult, ServiceConfig, ServiceState
from agent.probes import ProbeRunner
from agent.state_manager import StateManager
from agent.validator import StateValidator


PAYMENT = ServiceConfig(
    "payment-service",
    "http://payment",
    critical_dependencies=("postgres", "redis"),
)
START = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def result(
    second: int = 0,
    *,
    healthz: int | None = 200,
    readyz: int | None = 200,
    postgres: bool = True,
    redis: bool = True,
    error: str | None = None,
    latency_ms: float = 12.5,
) -> ProbeResult:
    return ProbeResult(
        service=PAYMENT.name,
        timestamp=START + timedelta(seconds=second),
        healthz_status=healthz,
        readyz_status=readyz,
        latency_ms=latency_ms,
        dependencies={"postgres": postgres, "redis": redis},
        error_reason=error,
    )


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        (result(), ServiceState.HEALTHY),
        (result(readyz=503, postgres=False), ServiceState.ZOMBIE),
        (result(readyz=503, redis=False), ServiceState.ZOMBIE),
        (result(healthz=None, readyz=None, error="ConnectError"), ServiceState.DOWN),
        (result(latency_ms=1750), ServiceState.DEGRADED),
    ],
)
def test_classifies_probe_evidence(evidence: ProbeResult, expected: ServiceState) -> None:
    state, _ = classify(PAYMENT, evidence)
    assert state == expected


class SequenceProbe:
    def __init__(self, results: list[ProbeResult]):
        self.results = iter(results)

    async def __call__(self) -> ProbeResult:
        return next(self.results)


@pytest.mark.asyncio
async def test_single_temporary_failure_does_not_change_confirmed_state() -> None:
    emitter = EventEmitter()
    manager = StateManager(failure_threshold=3, emitter=emitter)
    validator = StateValidator(failure_threshold=3, retry_delay_seconds=0)
    retry = SequenceProbe([result(1)])

    probes = await validator.collect(PAYMENT, result(0, healthz=None), ServiceState.HEALTHY, retry)
    for evidence in probes:
        status = manager.observe(PAYMENT, evidence)

    assert status.state == ServiceState.HEALTHY
    assert emitter.events == []
    assert status.first_failure_observed is None


@pytest.mark.asyncio
async def test_confirms_failure_after_threshold_and_records_detection_time() -> None:
    emitter = EventEmitter()
    manager = StateManager(failure_threshold=3, emitter=emitter)
    validator = StateValidator(failure_threshold=3, retry_delay_seconds=0)
    retry = SequenceProbe([result(1, readyz=503, postgres=False), result(3, readyz=503, postgres=False)])

    probes = await validator.collect(
        PAYMENT,
        result(0, readyz=503, postgres=False),
        ServiceState.HEALTHY,
        retry,
    )
    for evidence in probes:
        status = manager.observe(PAYMENT, evidence)

    assert status.state == ServiceState.ZOMBIE
    assert status.first_failure_observed == START
    assert status.failure_confirmed_at == START + timedelta(seconds=3)
    assert status.detection_time_seconds == 3
    assert emitter.events[-1].to_dict()["current_state"] == "ZOMBIE"


@pytest.mark.asyncio
async def test_requires_multiple_successes_to_confirm_recovery() -> None:
    manager = StateManager(failure_threshold=2, recovery_threshold=2)
    manager.observe(PAYMENT, result(0, healthz=None))
    manager.observe(PAYMENT, result(1, healthz=None))
    validator = StateValidator(failure_threshold=2, recovery_threshold=2, retry_delay_seconds=0)
    retry = SequenceProbe([result(4)])

    probes = await validator.collect(PAYMENT, result(3), ServiceState.DOWN, retry)
    for evidence in probes:
        status = manager.observe(PAYMENT, evidence)

    assert status.state == ServiceState.HEALTHY
    assert status.recovery_first_observed == START + timedelta(seconds=3)
    assert status.recovery_confirmed_at == START + timedelta(seconds=4)


@pytest.mark.asyncio
async def test_probe_runner_parses_readiness_dependencies() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            503,
            json={
                "status": "not_ready",
                "checks": {"postgres": {"ok": False}, "redis": {"ok": True}},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        evidence = await ProbeRunner(client=client).probe(PAYMENT)

    assert evidence.healthz_status == 200
    assert evidence.readyz_status == 503
    assert evidence.dependencies == {"postgres": False, "redis": True}