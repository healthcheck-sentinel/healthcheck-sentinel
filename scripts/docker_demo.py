"""Real Docker failure/recovery validation. Run from repository root.
Notifications are delivered to the local HTTP recorder, never to Slack.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ['docker', 'compose', '-f', str(ROOT/'docker-compose.yml'), '-f', str(ROOT/'docker-compose.demo.yml')]


def compose(*args):
    subprocess.run(COMPOSE + list(args), cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def get(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def status():
    return get('http://127.0.0.1:9101/status')


def wait_for(predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = status()
            if predicate(value):
                return value
        except (URLError, TimeoutError, KeyError):
            pass
        time.sleep(.2)
    raise RuntimeError('Timed out waiting for confirmed agent state')


def healthy(snapshot):
    services = snapshot.get('services', {})
    return len(services) == 3 and all(s['state'] == 'HEALTHY' for s in services.values())


def code(port, path):
    try:
        with urlopen(f'http://127.0.0.1:{port}/{path}', timeout=5) as r:
            return r.status
    except HTTPError as e:
        return e.code
    except URLError:
        return None


def now():
    return datetime.now(timezone.utc)


def seconds(timestamp, start):
    return (datetime.fromisoformat(timestamp) - start).total_seconds()


def scenario(service, cause):
    baseline = wait_for(healthy)
    prior_ids = {i['incident_id'] for i in baseline['incidents']}
    prior_messages = len(get('http://127.0.0.1:18080/messages'))
    started = now()
    expected = 'DOWN' if service == 'payment-service' else 'ZOMBIE'
    try:
        compose('stop', '-t', '1', service)
        endpoints = {name: {'healthz': code(port, 'healthz'), 'readyz': code(port, 'readyz')} for name, port in [('payment-service',8001),('order-service',8002)]}
        failed = wait_for(lambda s: any(i['incident_id'] not in prior_ids and i['root_cause'] == cause and i['status'] == 'ACTIVE' for i in s.get('incidents', [])))
        incidents = [i for i in failed['incidents'] if i['incident_id'] not in prior_ids]
        assert len(incidents) == 1, incidents
        incident = incidents[0]
        assert incident['state'] == expected
        affected = ['payment-service'] if expected == 'DOWN' else ['order-service','payment-service']
        assert incident['affected_services'] == affected
        for name in affected:
            assert failed['services'][name]['state'] == expected
            if expected == 'ZOMBIE':
                assert endpoints[name] == {'healthz':200,'readyz':503}
        print(f'{cause}: confirmed {expected}; holding failure for duplicate check', flush=True)
        time.sleep(7)
        repeated = status()
        assert len([i for i in repeated['incidents'] if i['incident_id'] not in prior_ids]) == 1
        active = [n for n in repeated['notifications'] if n['incident_id'] == incident['incident_id'] and n['status'] == 'ACTIVE']
        assert len(active) == 1 and active[0]['outcome'] == 'delivered'
    finally:
        recovery_started = now()
        compose('start', service)
    recovered = wait_for(lambda s: healthy(s) and any(i['incident_id'] == incident['incident_id'] and i['status'] == 'RESOLVED' for i in s.get('incidents', [])))
    resolved = next(i for i in recovered['incidents'] if i['incident_id'] == incident['incident_id'])
    notifications = [n for n in recovered['notifications'] if n['incident_id'] == incident['incident_id']]
    assert [n['status'] for n in notifications] == ['ACTIVE','RESOLVED']
    assert all(n['outcome'] == 'delivered' for n in notifications)
    messages = get('http://127.0.0.1:18080/messages')
    captured = [m for m in messages[prior_messages:] if m['payload']['text'].startswith(incident['incident_id'] + ':')]
    assert len(captured) == 2
    report = {
        'cause':cause, 'endpoints_during_failure':endpoints, 'incident':resolved,
        'injection_to_confirmation_seconds':seconds(incident['confirmation_time'],started),
        'first_failed_probe_to_confirmation_seconds':incident['detection_time_seconds'],
        'restart_to_recovery_seconds':seconds(resolved['recovery_time'], recovery_started),
        'confirmation_to_webhook_receipt_seconds':seconds(captured[0]['received_at'], datetime.fromisoformat(incident['confirmation_time'])),
        'notifications':notifications, 'captured_http_messages':len(captured),
        'duplicate_incidents':0,
    }
    print(json.dumps({k:v for k,v in report.items() if k not in ('incident','notifications')}, indent=2), flush=True)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--full', action='store_true', help='Also inject Redis, process crash, transient pause, and sample CPU')
    parser.add_argument('--output', default='docs/validation-results.json')
    args=parser.parse_args()
    baseline = wait_for(healthy)
    assert all(code(p,e) == 200 for p in (8001,8002,8003) for e in ('healthz','readyz'))
    result={'measured_at':now().isoformat(), 'environment':'Docker Desktop Linux; three services', 'notification_transport':'local HTTP webhook capture; not real Slack', 'baseline':'all healthz/readyz 200; all HEALTHY', 'scenarios':[]}
    for service,cause in ([('postgres','postgresql'),('redis','redis'),('payment-service','payment-service')] if args.full else [('postgres','postgresql')]):
        result['scenarios'].append(scenario(service,cause))
    if args.full:
        before=status()
        try:
            compose('pause','redis')
            time.sleep(.25)
        finally:
            compose('unpause','redis')
        time.sleep(8)
        after=wait_for(healthy)
        assert len(after['incidents']) == len(before['incidents'])
        assert len(after['notifications']) == len(before['notifications'])
        result['transient']={'pause_seconds':.25,'new_incidents':0,'new_notifications':0,'limitation':'Poll alignment is not guaranteed; deterministic transient suppression is also unit-tested.'}
        print('Sampling agent CPU over 60 seconds of healthy monitoring...', flush=True)
        first=status()
        time.sleep(60)
        last=status()
        wall=last['process_wall_seconds']-first['process_wall_seconds']
        result['cpu']={'sample_seconds':wall,'cpu_seconds':last['process_cpu_seconds']-first['process_cpu_seconds'],'percent_one_core':100*(last['process_cpu_seconds']-first['process_cpu_seconds'])/wall}
    with urlopen('http://127.0.0.1:9100/metrics') as response:
        metrics=response.read().decode()
    required=['healthcheck_service_status','healthcheck_probe_duration_seconds','healthcheck_probe_failures_total','healthcheck_detection_seconds','healthcheck_incidents_total','healthcheck_process_cpu_percent','healthcheck_process_memory_bytes']
    assert all(name in metrics for name in required)
    result['metrics_available']=required
    targets=get('http://127.0.0.1:9090/api/v1/targets')['data']['activeTargets']
    assert all(t['health']=='up' for t in targets)
    result['prometheus_targets']=[{'job':t['labels']['job'],'health':t['health']} for t in targets]
    result['probe_mean_seconds']=get('http://127.0.0.1:9090/api/v1/query?query=sum(healthcheck_probe_duration_seconds_sum)%2Fsum(healthcheck_probe_duration_seconds_count)')['data']['result']
    output=ROOT/args.output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'PASS: measured report written to {output}',flush=True)

if __name__ == '__main__':
    main()
