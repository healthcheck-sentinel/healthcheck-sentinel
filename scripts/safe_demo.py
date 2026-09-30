"""Explicit local demo: stop one service briefly, then restore it automatically."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

# Permit direct execution as documented, as well as imports by tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.local_action import SERVICES, require_local_engine

STATE_DIR = ROOT / '.sentinel-state'


def compose(action, service):
    if service not in SERVICES or action not in ('stop', 'start'):
        raise ValueError('Only application demo services can be stopped or started')
    args = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'), action]
    if action == 'stop':
        args += ['--timeout', '1']
    subprocess.run(args + [service], check=True, capture_output=True, timeout=20, cwd=ROOT)


def state_path(service):
    if service not in SERVICES:
        raise ValueError('Service is not allowed')
    return STATE_DIR / ('safe-demo-' + service + '.json')


def read_state(service):
    try:
        return json.loads(state_path(service).read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(service, data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Unique temporary path avoids collisions between recovery attempts.
    temporary = STATE_DIR / ('safe-demo-' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    temporary.replace(state_path(service))


def restore(service, run_id=None):
    current = read_state(service)
    if run_id is not None and (current.get('run_id') != run_id or current.get('restored')):
        return False
    compose('start', service)
    current['restored'] = True
    current['restored_at'] = time.time()
    write_state(service, current)
    return True


def watchdog(service, run_id):
    current = read_state(service)
    if current.get('run_id') != run_id or current.get('restored'):
        return
    current['watchdog_ready'] = True
    write_state(service, current)
    while True:
        current = read_state(service)
        if current.get('run_id') != run_id or current.get('restored'):
            return
        if time.time() >= current['deadline']:
            try:
                # Recheck locality; never follow a newly selected remote context.
                require_local_engine()
                restore(service, run_id)
                return
            except (OSError, ValueError, subprocess.SubprocessError):
                # If Docker is temporarily unavailable, recover when it returns.
                time.sleep(5)
        else:
            time.sleep(0.5)


def spawn_watchdog(service, run_id):
    kwargs = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL,
              'stderr': subprocess.DEVNULL, 'cwd': str(ROOT), 'close_fds': True}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    return subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                             '_watchdog', '--service', service, '--run-id', run_id], **kwargs)


def start(service, seconds=45):
    if not 30 <= seconds <= 60:
        raise ValueError('Demo duration must be between 30 and 60 seconds')
    require_local_engine()
    previous = read_state(service)
    if previous and not previous.get('restored'):
        raise ValueError('A demo lease exists; run restore before starting another demo')
    # Do not stop an already-failed/stopped service or create an ambiguous demo.
    info = subprocess.run(['docker', 'inspect', '--format', '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}', service],
                          check=True, capture_output=True, text=True, timeout=10)
    if info.stdout.strip() != 'true healthy':
        raise ValueError('Selected service must already be running and healthy')
    run_id = uuid.uuid4().hex
    write_state(service, {'run_id': run_id, 'deadline': time.time()+seconds,
                          'restored': False, 'watchdog_ready': False})
    try:
        child = spawn_watchdog(service, run_id)
        ready_by = time.monotonic()+5
        while not read_state(service).get('watchdog_ready'):
            if child.poll() is not None or time.monotonic() >= ready_by:
                raise RuntimeError('Recovery helper did not start; failure was not injected')
            time.sleep(0.05)
        compose('stop', service)
        print(f'DEMO: {service} stopped. The real agent will confirm DOWN and notify Slack.', flush=True)
        print(f'Automatic restore is scheduled within {seconds} seconds of starting this command.', flush=True)
        print('Keep the status page and Slack channel visible. Ctrl+C also restores the service.', flush=True)
        while True:
            current = read_state(service)
            if current.get('restored') or current.get('run_id') != run_id or time.time() >= current['deadline']:
                break
            time.sleep(0.25)
    finally:
        restore(service, run_id)
    print('RESTORED: service started. Allow repeated probes to confirm HEALTHY and send recovery.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'restore', '_watchdog'))
    parser.add_argument('--service', choices=SERVICES, default='payment-service')
    parser.add_argument('--seconds', type=int, default=45)
    parser.add_argument('--run-id', default='')
    args = parser.parse_args(argv)
    try:
        if args.action == '_watchdog':
            watchdog(args.service, args.run_id)
        elif args.action == 'restore':
            require_local_engine()
            restore(args.service)
            print('RESTORED: wait for HEALTHY confirmation and the real Slack recovery notification.')
        else:
            start(args.service, args.seconds)
    except KeyboardInterrupt:
        print('Demo interrupted; recovery was requested. Verify HEALTHY in the status page.')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print('Demo stopped safely. Check local Docker and run the restore command. No configuration was changed.')
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
