"""Read-only submission preflight; never prints environment secrets."""
import json
import subprocess
import sys
from urllib.request import urlopen


def fetch(url):
    with urlopen(url, timeout=5) as r:
        return json.load(r)


def main():
    failures = []
    try:
        subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], check=True, capture_output=True)
        print('PASS Docker engine reachable')
    except (OSError, subprocess.CalledProcessError):
        failures.append('Docker engine unavailable: start Docker Desktop Linux engine')
    for port in (8001, 8002, 8003):
        for path in ('healthz', 'readyz'):
            try:
                fetch(f'http://127.0.0.1:{port}/{path}')
                print(f'PASS {port}/{path}')
            except Exception:
                failures.append(f'{port}/{path} unavailable or unhealthy')
    try:
        s = fetch('http://127.0.0.1:9101/status')
        assert len(s['services']) == 3
        assert all(v['state'] == 'HEALTHY' for v in s['services'].values())
        print('PASS three confirmed HEALTHY service states')
    except Exception:
        failures.append('Agent status is not healthy')
    try:
        targets = fetch('http://127.0.0.1:9090/api/v1/targets')['data']['activeTargets']
        assert {'monitoring-agent', 'prometheus'} <= {t['labels']['job'] for t in targets}
        assert all(t['health'] == 'up' for t in targets)
        print('PASS Prometheus targets UP')
    except Exception:
        failures.append('Prometheus targets unavailable or DOWN')
    try:
        fetch('http://127.0.0.1:18080/messages')
        print('PASS local webhook recorder reachable (not real Slack)')
    except Exception:
        print('NOTE local webhook recorder unavailable; required for docker_demo.py')
    for failure in failures:
        print('FAIL', failure)
    return bool(failures)

if __name__ == '__main__':
    sys.exit(main())
