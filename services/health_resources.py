"""Read-only container resources and readiness instrumentation."""
import json
import os
import time
from pathlib import Path
import psutil

class ResourceSampler:
    def __init__(self, root='/sys/fs/cgroup'):
        self.root = Path(root)
        self.process = psutil.Process()
        self.previous = None
        self.started = time.monotonic()
        self.probe_cpu_seconds = 0.0
        self.probe_requests = 0

    def sample(self):
        vm = psutil.virtual_memory()
        used, limit, scope = vm.total - vm.available, vm.total, 'host'
        cpu_seconds = sum(self.process.cpu_times()[:2])
        cpu_scope = 'process'
        try:
            current = int((self.root / 'memory.current').read_text())
            maximum = (self.root / 'memory.max').read_text().strip()
            # Unlimited containers still have the host's finite memory headroom.
            used, limit, scope = current, vm.total if maximum == 'max' else int(maximum), 'container'
            available = min(max(0, limit - used), vm.available)
        except (OSError, ValueError):
            available = vm.available
        try:
            stat = dict(line.split() for line in (self.root / 'cpu.stat').read_text().splitlines())
            cpu_seconds = int(stat['usage_usec']) / 1e6
            cpu_scope = 'container'
        except (OSError, ValueError, KeyError):
            pass
        now = time.monotonic()
        cpu = None
        if self.previous and now > self.previous[0]:
            cpu = max(0.0, (cpu_seconds-self.previous[1])/(now-self.previous[0])*100)
        self.previous = (now, cpu_seconds)
        return {'memory_used_bytes': used, 'memory_limit_bytes': limit,
                'memory_available_bytes': available, 'memory_scope': scope,
                'cpu_seconds': cpu_seconds, 'cpu_percent': cpu, 'cpu_scope': cpu_scope,
                'process_cpu_seconds': sum(self.process.cpu_times()[:2]),
                'probe_cpu_seconds': self.probe_cpu_seconds,
                'probe_requests': self.probe_requests, 'monotonic_seconds': now}


def memory_check(resources):
    limit = resources['memory_limit_bytes']
    available = resources['memory_available_bytes']
    required = max(16*1024*1024, int(limit*0.05))
    return {'ok': available >= required, 'available_bytes': available,
            'required_bytes': required, 'scope': resources['memory_scope']}


class ResourceMiddleware:
    """Enrich only health responses; application routes are untouched."""
    def __init__(self, app):
        self.app = app
        self.sampler = ResourceSampler()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') not in ('/healthz', '/readyz'):
            return await self.app(scope, receive, send)
        started = time.process_time()
        start = None
        chunks = []
        async def capture(message):
            nonlocal start
            if message['type'] == 'http.response.start':
                start = dict(message)
            elif message['type'] == 'http.response.body':
                chunks.append(message.get('body', b''))
                if message.get('more_body', False):
                    return
                data = json.loads(b''.join(chunks))
                self.sampler.probe_requests += 1
                self.sampler.probe_cpu_seconds += max(0, time.process_time()-started)
                if scope['path'] == '/readyz':
                    resources = self.sampler.sample()
                    check = memory_check(resources)
                    data['resources'] = resources
                    data.setdefault('checks', {})['memory'] = check
                    if not check['ok']:
                        start['status'] = 503
                        data['status'] = 'not_ready'
                body = json.dumps(data).encode()
                start['headers'] = [(k,v) for k,v in start['headers'] if k.lower()!=b'content-length']
                start['headers'].append((b'content-length', str(len(body)).encode()))
                await send(start)
                await send({'type': 'http.response.body', 'body': body})
        await self.app(scope, receive, capture)
