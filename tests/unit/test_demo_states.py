import json
import os
import time
import httpx
import pytest
from fastapi import FastAPI
from services.payment_service.demo_latency import DemoLatency
from agent.probes import ProbeRunner
from agent.classifier import classify
from tests.unit.test_monitoring_agent import PAYMENT
from scripts import demo_states

@pytest.mark.parametrize('mode,expected',[('degraded','DEGRADED'),('healthy','HEALTHY')])
@pytest.mark.asyncio
async def test_real_probe_classifies_demo_and_expiry(tmp_path,mode,expected):
    app=FastAPI()
    @app.get('/healthz')
    def live():return {'status':'ok'}
    @app.get('/readyz')
    def ready():return {'checks':{'postgres':{'ok':True},'redis':{'ok':True}}}
    path=tmp_path/'lease.json'
    path.write_text(json.dumps({'mode':mode,'latency_ms':2000,'issued_at':time.time(),'expires_at':time.time()+45 if mode == 'degraded' else time.time()}))
    wrapped=DemoLatency(app,path,True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped),base_url=PAYMENT.base_url) as client:
        result=await ProbeRunner(client=client).probe(PAYMENT)
        assert result.healthz_status==200 and result.readyz_status==200
        assert result.dependencies=={'postgres':True,'redis':True}
        if mode == 'degraded':
            assert result.latency_ms >= 1900
        assert classify(PAYMENT,result)[0].value==expected
        path.write_text(json.dumps({'mode':'degraded','latency_ms':2000,'issued_at':time.time()-50,'expires_at':time.time()-5}))
        assert classify(PAYMENT,await ProbeRunner(client=client).probe(PAYMENT))[0].value=='HEALTHY'

@pytest.mark.parametrize('enabled,lease',[(False,{'mode':'zombie','issued_at':0,'expires_at':99999999999}),(True,{'mode':'zombie','issued_at':0,'expires_at':99999999999}),(True,{'mode':'other','issued_at':time.time(),'expires_at':time.time()+45}),(True,{})])
def test_override_rejects_disabled_invalid_or_unbounded_leases(tmp_path,enabled,lease):
    path=tmp_path/'lease';path.write_text(json.dumps(lease))
    assert DemoLatency(None,path,enabled).delay_seconds() == 0

@pytest.mark.asyncio
async def test_latency_injection_does_not_delay_business_requests(tmp_path):
    app=FastAPI()
    @app.get('/payments')
    def payments():return {'usable':True}
    path=tmp_path/'lease.json'
    path.write_text(json.dumps({'mode':'degraded','latency_ms':2000,'issued_at':time.time(),'expires_at':time.time()+45}))
    wrapped=DemoLatency(app,path,True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped),base_url=PAYMENT.base_url) as client:
        started=time.perf_counter()
        response=await client.get('/payments')
    assert response.json()=={'usable':True}
    assert time.perf_counter()-started < 0.5


def test_lease_write_uses_unique_atomic_file_and_cleans_stale_temp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_states, "DIRECTORY", tmp_path)
    stale = tmp_path / "payment-service-stale.tmp"
    stale.write_text("stale", encoding="utf-8")
    old = time.time() - 120
    os.utime(stale, (old, old))

    demo_states.write_lease("degraded", seconds=45)

    lease = json.loads((tmp_path / "payment-service.json").read_text(encoding="utf-8"))
    assert lease["mode"] == "degraded"
    assert lease["issued_at"] < lease["expires_at"]
    assert not stale.exists()
    assert list(tmp_path.glob("payment-service-*.tmp")) == []
