import asyncio
import importlib
from unittest.mock import AsyncMock, Mock
import httpx
import pytest
from prometheus_client import CollectorRegistry
from services.health_resources import ResourceSampler, memory_check
from services.probe_pool import ProbePool
from agent.probes import _parse_resources, _parse_pools
from agent.metrics import MetricsCollector
from agent.models import ProbeResult, utc_now, ServiceState
from agent.classifier import classify
from agent.root_cause import RootCauseAnalyzer
from tests.unit.test_monitoring_agent import PAYMENT


def test_cgroup_memory_and_cpu(tmp_path,monkeypatch):
    clock=iter([0.0,1.0,2.0])
    monkeypatch.setattr("services.health_resources.time.monotonic",lambda:next(clock))
    (tmp_path/'memory.current').write_text('500')
    (tmp_path/'memory.max').write_text('1000')
    (tmp_path/'cpu.stat').write_text('usage_usec 1000000\n')
    sampler=ResourceSampler(tmp_path)
    one=sampler.sample()
    assert one['memory_scope']=='container'
    assert one['memory_available_bytes']==500
    assert one['cpu_seconds']==1
    assert one['cpu_percent'] is None
    assert sampler.sample()['cpu_percent']==0


def test_host_fallback_and_unlimited_container(tmp_path):
    sampler=ResourceSampler(tmp_path)
    assert sampler.sample()['memory_scope']=='host'
    (tmp_path/'memory.current').write_text('500')
    (tmp_path/'memory.max').write_text('max')
    assert sampler.sample()['memory_available_bytes']>0

@pytest.mark.parametrize('available,expected',[(0,False),(100,False),(100*1024*1024,True)])
def test_memory_headroom(available,expected):
    assert memory_check({'memory_limit_bytes':1024*1024*1024,'memory_available_bytes':available,'memory_scope':'container'})['ok'] is expected

@pytest.mark.parametrize('service', ['payment','order','user'])
@pytest.mark.asyncio
async def test_memory_pressure_readiness_not_liveness(service,monkeypatch):
    module=importlib.import_module(f'services.{service}_service.main')
    if service!='user':
        monkeypatch.setattr(module,'run_readiness_checks',AsyncMock(return_value={'ready':True,'checks':{'postgres':{'ok':True},'redis':{'ok':True}}}))
    monkeypatch.setattr(ResourceSampler,'sample',lambda self:{'memory_limit_bytes':1000000000,'memory_available_bytes':0,'memory_scope':'container'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as client:
        assert (await client.get('/healthz')).status_code==200
        response=await client.get('/readyz')
        assert response.status_code==503
        assert response.json()['checks']['memory']['ok'] is False
        assert (await client.get('/')).status_code==200

@pytest.mark.asyncio
async def test_pool_bounds_reuse_timeout_and_recovery():
    connect=AsyncMock(side_effect=[object(),object()]);close=AsyncMock()
    pool=ProbePool(connect,close,maximum=1,acquire_timeout=0.01)
    async with pool.acquire() as first:
        assert pool.snapshot()['in_use']==1
        with pytest.raises(asyncio.TimeoutError):
            async with pool.acquire():
                pass
    async with pool.acquire() as reused:
        assert reused is first
    with pytest.raises(RuntimeError):
        async with pool.acquire():
            raise RuntimeError('broken')
    close.assert_awaited_once_with(first)
    async with pool.acquire() as replacement:
        assert replacement is not first
    assert pool.snapshot()['available']==1
    await pool.close()
    assert pool.snapshot()['idle']==0

@pytest.mark.asyncio
async def test_pool_connect_failure_and_cancellation_release_capacity():
    pool=ProbePool(AsyncMock(side_effect=OSError),AsyncMock(),maximum=1)
    with pytest.raises(OSError):
        async with pool.acquire():pass
    assert pool.snapshot()['available']==1
    pool.connect=AsyncMock(return_value=object())
    with pytest.raises(asyncio.CancelledError):
        async with pool.acquire():raise asyncio.CancelledError()
    assert pool.snapshot()['available']==1

@pytest.mark.parametrize('service',['payment','order'])
@pytest.mark.asyncio
async def test_successful_pooled_checks_and_metadata(service,monkeypatch):
    module=importlib.import_module(f'services.{service}_service.checks')
    conn=Mock(fetchval=AsyncMock(return_value=1),fetchrow=AsyncMock(return_value={'used':4,'capacity':100}),close=AsyncMock())
    redis=Mock(ping=AsyncMock(return_value=True),info=AsyncMock(return_value={'connected_clients':3,'maxclients':100}),aclose=AsyncMock())
    monkeypatch.setattr(module,'postgres_pool',ProbePool(AsyncMock(return_value=conn),AsyncMock()))
    monkeypatch.setattr(module,'redis_pool',ProbePool(AsyncMock(return_value=redis),AsyncMock()))
    response=await module.run_readiness_checks()
    assert response['ready']
    assert response['checks']['postgres']['pool']['max_connections']==2
    assert response['checks']['redis']['server_connections']['used']==3
    conn.fetchrow.side_effect=PermissionError
    redis.info.side_effect=PermissionError
    assert (await module.run_readiness_checks())['ready']
    redis.ping.side_effect=OSError
    assert not (await module.check_redis())['ok']
    await module.close_pools()


def test_resource_parse_rejects_untrusted_strings_and_nonfinite():
    assert _parse_resources({'resources':{'cpu_percent':float('nan'),'memory_available_bytes':42,'secret':'hidden','cpu_seconds':True}})=={'memory_available_bytes':42}
    assert _parse_pools({'checks':{'postgres':{'pool':{'max_connections':2,'secret':'hidden'}}}})['postgres']['pool']=={'max_connections':2}


def test_target_metrics_and_service_scoped_memory_root_cause():
    evidence=ProbeResult('payment-service',utc_now(),200,503,1,{'postgres':True,'redis':True,'memory':False},resources={'cpu_percent':0.2},pools={'postgres':{'pool':{'available':2}}})
    assert classify(PAYMENT,evidence)[0]==ServiceState.DEGRADED
    assert RootCauseAnalyzer().identify_service_root_causes({'service':'payment-service','state':'DEGRADED','evidence':evidence.to_dict()})==['payment-service:memory']
    metrics=MetricsCollector(CollectorRegistry());metrics.record_probe('payment-service',evidence)
    assert metrics.registry.get_sample_value('healthcheck_target_resource',{'service':'payment-service','resource':'cpu_percent'})==0.2
    assert metrics.registry.get_sample_value('healthcheck_dependency_pool_connections',{'service':'payment-service','dependency':'postgres','kind':'pool_available'})==2
