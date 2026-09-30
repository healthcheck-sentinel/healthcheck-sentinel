from datetime import timedelta
from unittest.mock import Mock
import httpx
import pytest
from prometheus_client import CollectorRegistry
from agent.metrics import MetricsCollector
from agent.incidents import IncidentManager
from agent.root_cause import RootCauseAnalyzer
from agent.state_manager import StateManager
from agent.models import ServiceState
from chatops.slack_client import SlackClient
from tests.unit.test_monitoring_agent import PAYMENT, result
from tests.unit.test_root_cause_and_incidents import make_status


def test_zombie_can_become_down_and_back():
    manager = StateManager(failure_threshold=1)
    manager.observe(PAYMENT, result(readyz=503, postgres=False))
    assert manager.observe(PAYMENT, result(1, healthz=None, readyz=None)).state == ServiceState.DOWN
    assert manager.observe(PAYMENT, result(2, readyz=503, postgres=False)).state == ServiceState.ZOMBIE


def test_pending_recovery_retains_root_cause():
    manager = StateManager(failure_threshold=1, recovery_threshold=2)
    incidents = IncidentManager()
    manager.observe(PAYMENT, result(readyz=503, postgres=False))
    incidents.process_statuses(manager.statuses)
    manager.observe(PAYMENT, result(1))
    incidents.process_statuses(manager.statuses)
    assert len(incidents.get_all_incidents()) == 1
    assert incidents.get_active_incidents()[0].root_cause == 'postgresql'
    manager.observe(PAYMENT, result(2))
    incidents.process_statuses(manager.statuses)
    assert len(incidents.get_resolved_incidents()) == 1


def test_missing_service_is_not_recovery():
    incidents = IncidentManager()
    incidents.process_statuses({'payment-service': make_status('payment-service', ServiceState.ZOMBIE, readyz=503, postgres=False)})
    incidents.process_statuses({})
    assert len(incidents.get_active_incidents()) == 1


def test_down_root_cause_is_process_even_with_dependency_evidence():
    status = make_status('payment-service', ServiceState.DOWN, healthz=None, postgres=False)
    assert RootCauseAnalyzer().identify_service_root_causes(status) == ['payment-service']


def test_active_metric_clears_on_recovery():
    metrics = MetricsCollector(CollectorRegistry())
    manager = IncidentManager()
    manager.process_statuses({'payment-service': make_status('payment-service', ServiceState.ZOMBIE, readyz=503, postgres=False)})
    metrics.record_incidents(manager.get_all_incidents())
    manager.process_statuses({'payment-service': make_status('payment-service', ServiceState.HEALTHY, second=10)})
    metrics.record_incidents(manager.get_all_incidents())
    assert metrics.registry.get_sample_value('healthcheck_active_incidents', {'root_cause': 'postgresql'}) == 0


def test_cpu_sampler_is_reused():
    metrics = MetricsCollector(CollectorRegistry())
    proc = Mock()
    proc.cpu_percent.return_value = 1.5
    proc.memory_info.return_value.rss = 1234
    metrics._process = proc
    assert metrics.update_resource_usage() == (1.5, 1234)


def test_slack_http_200_api_error_is_failure(monkeypatch):
    monkeypatch.delenv('SLACK_WEBHOOK_URL', raising=False)
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: httpx.Response(200, json={'ok': False, 'error': 'invalid_auth'}, request=httpx.Request('POST','https://slack.com/api/chat.postMessage')))
    with pytest.raises(RuntimeError, match='rejected'):
        SlackClient(bot_token='test').send_message({'text': 'test'})


def test_slack_stale_signed_request_rejected():
    import hashlib, hmac
    body, timestamp, secret = b'test', '1700000000', 'test'
    signature = 'v0=' + hmac.new(secret.encode(), f'v0:{timestamp}:'.encode()+body, hashlib.sha256).hexdigest()
    assert not SlackClient(signing_secret=secret).verify_request(body, timestamp, signature)


@pytest.mark.asyncio
async def test_probe_count_once_per_actual_request():
    from agent.main import MonitoringAgent
    from agent.chatops_dispatcher import ChatOpsEventDispatcher
    class Probes:
        async def probe(self, config):
            return result()
    metrics = MetricsCollector(CollectorRegistry())
    agent = MonitoringAgent(registry=(PAYMENT,), probe_runner=Probes(), metrics_collector=metrics)
    await agent.poll_once()
    assert metrics.registry.get_sample_value('healthcheck_probe_duration_seconds_count', {'service': PAYMENT.name, 'probe_type': 'combined'}) == 1


def test_optional_failure_is_degraded():
    from agent.classifier import classify
    from dataclasses import replace
    evidence = replace(result(), dependencies={'postgres': True, 'redis': True, 'cache_optional': False})
    assert classify(PAYMENT, evidence)[0] == ServiceState.DEGRADED

@pytest.mark.parametrize('module_name', ['services.payment_service.main', 'services.order_service.main'])
@pytest.mark.asyncio
async def test_real_asgi_routes_preserve_liveness_on_dependency_failure(module_name, monkeypatch):
    import importlib
    module = importlib.import_module(module_name)
    async def failure():
        return {'ready': False, 'checks': {'postgres': {'ok': False}, 'redis': {'ok': True}}}
    monkeypatch.setattr(module, 'run_readiness_checks', failure)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as client:
        assert (await client.get('/healthz')).status_code == 200
        ready = await client.get('/readyz')
        assert ready.status_code == 503
        assert ready.json()['checks']['postgres']['ok'] is False

@pytest.mark.parametrize('service', ['payment','order'])
@pytest.mark.asyncio
async def test_postgres_query_timeout_closes_connection(service, monkeypatch):
    import importlib, asyncio
    from unittest.mock import AsyncMock
    module = importlib.import_module(f'services.{service}_service.checks')
    connection = Mock()
    connection.fetchval = AsyncMock(side_effect=asyncio.TimeoutError)
    connection.close = AsyncMock()
    monkeypatch.setattr(module.asyncpg, 'connect', AsyncMock(return_value=connection))
    assert (await module.check_postgres())['ok'] is False
    connection.close.assert_awaited_once()


def test_http_error_response_does_not_mean_process_unreachable():
    from agent.classifier import classify
    assert classify(PAYMENT,result(healthz=500))[0] == ServiceState.DEGRADED

@pytest.mark.asyncio
async def test_transient_failure_never_creates_incident_or_alert():
    from dataclasses import replace
    from agent.main import MonitoringAgent
    from agent.chatops_dispatcher import ChatOpsEventDispatcher
    from unittest.mock import Mock
    class TransientProbes:
        def __init__(self):
            self.calls = 0
        async def probe(self, config):
            self.calls += 1
            return result(self.calls, readyz=503, postgres=False) if self.calls == 1 else result(self.calls)
    transport = Mock()
    agent = MonitoringAgent(registry=(PAYMENT,), probe_runner=TransientProbes(), failure_threshold=3, retry_delay_seconds=0, metrics_collector=MetricsCollector(CollectorRegistry()), chatops_dispatcher=ChatOpsEventDispatcher(slack_client=transport))
    states = await agent.poll_once()
    assert states[PAYMENT.name]['state'] == 'HEALTHY'
    assert agent.incidents.get_all_incidents() == []
    transport.send_message.assert_not_called()


def test_alert_does_not_copy_private_error_strings():
    from chatops.messages import build_incident_alert
    from chatops.models import Incident
    from tests.unit.test_chatops import INCIDENT_PAYLOAD
    incident = Incident.from_dict({**INCIDENT_PAYLOAD, 'evidence': {'payment-service': {'healthz_status':200, 'readyz_status':503, 'dependencies':{'postgres':False}, 'error_reason':'secret-value-in-private-url'}}})
    payload = str(build_incident_alert(incident))
    assert 'postgres' in payload
    assert 'secret-value-in-private-url' not in payload
