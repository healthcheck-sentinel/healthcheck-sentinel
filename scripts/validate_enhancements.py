"""Real Docker outage/recovery verification using the configured ChatOps transport."""
import json
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]

def get(url):
    with urlopen(url,timeout=5) as response:return json.load(response)

def status():return get('http://127.0.0.1:9101/status')

def wait_for(predicate,timeout=55):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        snapshot=status()
        if predicate(snapshot):return snapshot
        time.sleep(0.25)
    raise AssertionError('Timed out waiting for confirmed state')

def healthy(s):return len(s['services'])==3 and all(v['state']=='HEALTHY' for v in s['services'].values())

def compose(action,service):
    subprocess.run(['docker','compose','-f',str(ROOT/'docker-compose.yml'),action,service],check=True,capture_output=True)

def code(url):
    try:
        with urlopen(url,timeout=5) as response:return response.status
    except HTTPError as error:return error.code

def scenario(service,cause,state):
    before=wait_for(healthy);prior={i['incident_id'] for i in before['incidents']}
    started=time.monotonic();incident=None
    try:
        compose('stop',service)
        failed=wait_for(lambda s:any(i['root_cause']==cause and i['status']=='ACTIVE' and i['incident_id'] not in prior for i in s['incidents']))
        detected=time.monotonic()-started
        incidents=[i for i in failed['incidents'] if i['incident_id'] not in prior]
        assert len(incidents)==1
        incident=incidents[0];assert incident['state']==state
        if state=='ZOMBIE':
            for port in (8001,8002):
                assert code(f'http://127.0.0.1:{port}/healthz')==200
                assert code(f'http://127.0.0.1:{port}/readyz')==503
            assert incident['affected_services']==['order-service','payment-service']
        assert incident['evidence'].get('_adjacent_resources')
        time.sleep(9)
        held=status()
        assert len([i for i in held['incidents'] if i['incident_id'] not in prior])==1
        notices=[n for n in held['notifications'] if n['incident_id']==incident['incident_id']]
        assert len(notices)==1 and notices[0]['outcome']=='delivered'
    finally:
        recovery=time.monotonic();compose('start',service)
    resolved=wait_for(lambda s:healthy(s) and any(i['incident_id']==incident['incident_id'] and i['status']=='RESOLVED' for i in s['incidents']))
    recovered=time.monotonic()-recovery
    notices=[n for n in resolved['notifications'] if n['incident_id']==incident['incident_id']]
    assert [n['status'] for n in notices]==['ACTIVE','RESOLVED']
    assert all(n['outcome']=='delivered' for n in notices)
    return {'service':service,'state':state,'detection_seconds':detected,'recovery_seconds':recovered,
            'incident_notifications':1,'recovery_notifications':1,'duplicate_notifications':0,
            'delivery_evidence':'configured transport returned success; Slack UI not inspected'}

def main():
    wait_for(healthy)
    results=[]
    for row in [('postgres','postgresql','ZOMBIE'),('redis','redis','ZOMBIE'),('payment-service','payment-service','DOWN')]:
        print('Testing '+row[0]+'; sends configured incident/recovery notifications.',flush=True)
        result=scenario(*row);results.append(result);print(json.dumps(result),flush=True)
    with urlopen('http://127.0.0.1:9100/metrics',timeout=5) as response:metrics=response.read().decode()
    assert 'healthcheck_target_resource' in metrics and 'healthcheck_dependency_pool_connections' in metrics
    snapshot=wait_for(healthy)
    for name,item in snapshot['services'].items():
        assert item['evidence']['resources']['memory_available_bytes']>0
        if name!='user-service':assert item['evidence']['pools']['postgres']['pool']['max_connections']==2
    report={'scenarios':results,'metrics_verified':True,'healthy_after_recovery':True}
    Path('docs/enhancement-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS: real failure/recovery and resource metrics verified',flush=True)

if __name__=='__main__':main()
