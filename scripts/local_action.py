"""Allowlisted local operator actions. No HTTP server and no shell evaluation."""
import argparse
import os
from pathlib import Path
import subprocess

SERVICES = ('payment-service', 'order-service', 'user-service')
ROOT = Path(__file__).resolve().parents[1]


def command(action, service, lines=100):
    if service not in SERVICES or action not in ('logs', 'restart'):
        raise ValueError('Action or service is not allowed')
    if not isinstance(lines, int) or isinstance(lines, bool) or not 1 <= lines <= 500:
        raise ValueError('Log line count must be between 1 and 500')
    prefix = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml')]
    return prefix + (['logs', '--no-color', '--tail', str(lines), service] if action == 'logs' else ['restart', '--no-deps', '-t', '10', service])


def require_local_engine():
    # Reject overrides rather than accidentally performing an action on a remote host.
    if os.getenv('DOCKER_HOST') or os.getenv('DOCKER_CONTEXT'):
        raise ValueError('Unset DOCKER_HOST/DOCKER_CONTEXT and select a local Docker context first')
    result = subprocess.run(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], check=True, capture_output=True, text=True, timeout=10)
    if not result.stdout.strip().startswith(('npipe://', 'unix://')):
        raise ValueError('Only a local Unix socket or Windows named-pipe Docker engine is allowed')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('logs', 'restart'))
    parser.add_argument('service', choices=SERVICES)
    parser.add_argument('--lines', type=int, default=100)
    parser.add_argument('--confirm-restart', action='store_true', help='Explicitly authorize restarting the named application service')
    args = parser.parse_args(argv)
    if args.action == 'restart' and not args.confirm_restart:
        parser.error('Restart requires --confirm-restart; only the named application service is affected')
    try:
        cmd = command(args.action, args.service, args.lines)
        require_local_engine()
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=45)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        # Avoid printing remote endpoints or arbitrary subprocess exception details.
        print(f'Action failed safely ({type(exc).__name__}). Check Docker and the selected local context.')
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
