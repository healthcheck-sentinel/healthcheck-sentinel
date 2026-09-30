import hashlib
import hmac
import json
import time
import threading
from urllib.parse import urlencode
import pytest
from fastapi.testclient import TestClient
from chatops.interactive import create_app, action_blocks, safe_response_url, redact_logs, ActionGate

SECRET='local-test-signing-value'

def payload(action='sentinel_logs',service='payment-service'):
    return {'type':'block_actions','team':{'id':'TTEST'},'user':{'id':'UTEST'},'channel':{'id':'CTEST'},
            'actions':[{'action_id':action,'value':service,'action_ts':str(time.time())}],
            'response_url':'https://hooks.slack.com/actions/test-only'}

def signed(data,age=0):
    body=urlencode({'payload':json.dumps(data)}).encode();timestamp=str(int(time.time())-age)
    signature='v0='+hmac.new(SECRET.encode(),b'v0:'+timestamp.encode()+b':'+body,hashlib.sha256).hexdigest()
    return body,{'x-slack-request-timestamp':timestamp,'x-slack-signature':signature,'content-type':'application/x-www-form-urlencoded'}

def app(tmp_path,executor=lambda *a:'safe logs',deliver=lambda *a:None):
    return create_app(SECRET,'TTEST',{'UTEST'},{'CTEST'},tmp_path/'state.sqlite3',executor,deliver)

@pytest.mark.parametrize('action',['sentinel_logs','sentinel_restart'])
def test_signed_action_and_replay(tmp_path,action):
    called=[];done=threading.Event();messages=[]
    def deliver(url,body):messages.append(body);done.set()
    body,headers=signed(payload(action))
    with TestClient(app(tmp_path,lambda *args:called.append(args) or 'done',deliver)) as client:
        started=time.monotonic();response=client.post('/slack/actions',content=body,headers=headers)
        assert response.status_code==200 and time.monotonic()-started<3
        assert done.wait(2)
        assert client.post('/slack/actions',content=body,headers=headers).status_code==200
    assert len(called)==1
    assert messages[0]['response_type']=='ephemeral'
    assert not messages[0]['replace_original']

@pytest.mark.parametrize('change,status',[
    ('user',403),('team',403),('channel',403),('service',400),('action',400),
    ('response_url',400),('nan_timestamp',400),('stale',401),('signature',401)])
def test_reject_unsafe_requests(tmp_path,change,status):
    data=payload();called=[]
    if change in ('user','team','channel'):data[change]['id']='OTHER'
    if change=='service':data['actions'][0]['value']='postgres; command'
    if change=='action':data['actions'][0]['action_id']='anything'
    if change=='response_url':data['response_url']='http://127.0.0.1:9101/status'
    if change=='nan_timestamp':data['actions'][0]['action_ts']='nan'
    body,headers=signed(data,age=400 if change=='stale' else 0)
    if change=='signature':headers['x-slack-signature']='invalid'
    with TestClient(app(tmp_path,lambda *a:called.append(a))) as client:
        assert client.post('/slack/actions',content=body,headers=headers).status_code==status
    assert called==[]

@pytest.mark.parametrize('url',['https://hooks.slack.com.evil/actions/a','https://hooks.slack.com@evil/actions/a','https://hooks.slack.com:444/actions/a','http://hooks.slack.com/actions/a','https://hooks.slack.com/actions/a?x=1'])
def test_response_url_allowlist(url):assert not safe_response_url(url)

def test_persistent_gate_and_cooldown(tmp_path):
    path=tmp_path/'gate.db'
    assert ActionGate(path).reserve('one','payment-service','restart')
    assert not ActionGate(path).reserve('one','payment-service','restart')
    assert not ActionGate(path).reserve('two','payment-service','restart')
    assert ActionGate(path).reserve('three','order-service','restart')

def test_buttons_confirmation_and_opt_in(monkeypatch):
    from chatops.messages import build_incident_alert
    from chatops.models import Incident
    from tests.unit.test_chatops import INCIDENT_PAYLOAD
    monkeypatch.setenv('SLACK_ACTIONS_ENABLED','true')
    result=build_incident_alert(Incident.from_dict(INCIDENT_PAYLOAD))
    actions=[b for b in result['blocks'] if b['type']=='actions']
    assert len(actions)==2
    assert actions[0]['elements'][1]['confirm']['confirm']['text']=='Restart'
    assert action_blocks(['postgres','redis','untrusted'])==[]

def test_log_redaction(monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD','sensitive-test-value')
    assert 'sensitive-test-value' not in redact_logs('password=sensitive-test-value')
    assert 'example.internal' not in redact_logs('https://example.internal/secret')
    assert 'private-db-password' not in redact_logs('postgresql://user:private-db-password@internal/db')
    assert 'private-bearer-token' not in redact_logs('Authorization: Bearer private-bearer-token')
    assert len(redact_logs('x'*10000))<=2600

def test_reject_missing_configuration(monkeypatch,tmp_path):
    monkeypatch.delenv('SLACK_SIGNING_SECRET',raising=False)
    with pytest.raises(ValueError):create_app(state_path=tmp_path/'none.db')

def test_body_limit_and_no_public_docs(tmp_path):
    with TestClient(app(tmp_path)) as client:
        assert client.post('/slack/actions',content=b'x'*65537).status_code==413
        assert client.get('/docs').status_code==404


def test_signed_handler_acks_before_slow_action_finishes(tmp_path):
    started=threading.Event();release=threading.Event()
    def slow(*args):
        started.set();release.wait(2);return 'done'
    body,headers=signed(payload())
    with TestClient(app(tmp_path,slow)) as client:
        response=client.post('/slack/actions',content=body,headers=headers)
        assert response.status_code==200 and started.wait(1)
        assert not release.is_set()
        release.set()

def test_local_executor_uses_bounded_allowlisted_command(monkeypatch):
    import io
    from unittest.mock import Mock
    from chatops.interactive import execute_local
    import scripts.local_action as local
    monkeypatch.setattr(local,'require_local_engine',lambda:None)
    process=Mock(stdout=io.BytesIO(b'password=do-not-display\n'),wait=Mock(return_value=0),poll=Mock(return_value=0))
    calls=[]
    def spawn(args,**kwargs):calls.append((args,kwargs));return process
    monkeypatch.setattr('chatops.interactive.subprocess.Popen',spawn)
    output=execute_local('logs','payment-service')
    assert 'do-not-display' not in output
    assert calls[0][0][-1]=='payment-service'
    assert calls[0][0][-3:-1]==['--tail','50']
    assert 'shell' not in calls[0][1]

def test_resource_context_in_slack_is_numeric_only():
    from chatops.messages import build_incident_alert
    from chatops.models import Incident
    from tests.unit.test_chatops import INCIDENT_PAYLOAD
    data={**INCIDENT_PAYLOAD,'evidence':{'_adjacent_resources':{'user-service':{'cpu_percent':0.3,'memory_available_bytes':104857600,'secret':'never-copy'}}}}
    text=str(build_incident_alert(Incident.from_dict(data)))
    assert '100.0 MiB' in text and 'never-copy' not in text
