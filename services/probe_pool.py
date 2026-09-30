"""Small bounded pools for health probes; no unbounded connection creation."""
import asyncio
from contextlib import asynccontextmanager

class ProbePool:
    def __init__(self, connect, close, maximum=2, acquire_timeout=0.25):
        self.connect, self.close_connection = connect, close
        self.maximum, self.acquire_timeout = maximum, acquire_timeout
        self._loop = None
        self.idle = []
        self.in_use = 0
        self.waiting = 0

    def _initialize(self):
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self.semaphore = asyncio.Semaphore(self.maximum)
            self.idle = []
            self.in_use = self.waiting = 0

    def snapshot(self):
        return {'max_connections': self.maximum, 'in_use': self.in_use,
                'idle': len(self.idle), 'waiting': self.waiting,
                'available': self.maximum-self.in_use}

    @asynccontextmanager
    async def acquire(self):
        self._initialize()
        self.waiting += 1
        try:
            await asyncio.wait_for(self.semaphore.acquire(), self.acquire_timeout)
        finally:
            self.waiting -= 1
        self.in_use += 1
        connection = None
        try:
            connection = self.idle.pop() if self.idle else await self.connect()
            yield connection
        except BaseException:
            if connection is not None:
                try:
                    await self.close_connection(connection)
                finally:
                    connection = None
            raise
        finally:
            if connection is not None:
                self.idle.append(connection)
            self.in_use -= 1
            self.semaphore.release()

    async def close(self):
        while self.idle:
            await self.close_connection(self.idle.pop())
