"""Bounded, read-only database/cache health probes with pool evidence."""
import asyncio
import asyncpg
import redis.asyncio as aioredis
from services.probe_pool import ProbePool
from .config import settings

async def _connect_postgres():
    return await asyncio.wait_for(asyncpg.connect(settings.order_db_url), settings.db_connect_timeout)

async def _close_postgres(conn):
    try:
        await asyncio.wait_for(conn.close(), 0.2)
    except Exception:
        conn.terminate()

async def _connect_redis():
    return aioredis.from_url(settings.order_redis_url, max_connections=1,
        socket_connect_timeout=settings.redis_connect_timeout,
        socket_timeout=settings.redis_connect_timeout)

async def _close_redis(client):
    await asyncio.wait_for(client.aclose(), 0.2)

postgres_pool = ProbePool(_connect_postgres, _close_postgres)
redis_pool = ProbePool(_connect_redis, _close_redis)

async def check_postgres():
    try:
        async with postgres_pool.acquire() as conn:
            await asyncio.wait_for(conn.fetchval('SELECT 1'), settings.db_connect_timeout)
            result = {'ok': True, 'detail': 'reachable'}
            # Aggregate counts only: never return connection URLs or session identities.
            try:
                row = await asyncio.wait_for(conn.fetchrow(
                    "SELECT count(*) AS used, current_setting('max_connections')::int AS capacity FROM pg_stat_activity"),
                    settings.db_connect_timeout)
                result['server_connections'] = {'used': int(row['used']), 'capacity': int(row['capacity'])}
            except Exception:
                result['capacity_available'] = False
        result['pool'] = postgres_pool.snapshot()
        return result
    except Exception as exc:
        return {'ok': False, 'detail': type(exc).__name__, 'pool': postgres_pool.snapshot()}

async def check_redis():
    try:
        async with redis_pool.acquire() as client:
            await asyncio.wait_for(client.ping(), settings.redis_connect_timeout)
            result = {'ok': True, 'detail': 'reachable'}
            try:
                info = await asyncio.wait_for(client.info('clients'), settings.redis_connect_timeout)
                result['server_connections'] = {'used': int(info['connected_clients']), 'capacity': int(info['maxclients'])}
            except Exception:
                result['capacity_available'] = False
        result['pool'] = redis_pool.snapshot()
        return result
    except Exception as exc:
        return {'ok': False, 'detail': type(exc).__name__, 'pool': redis_pool.snapshot()}

async def run_readiness_checks():
    postgres, redis = await asyncio.gather(check_postgres(), check_redis())
    return {'ready': postgres['ok'] and redis['ok'], 'checks': {'postgres': postgres, 'redis': redis}}

async def close_pools():
    await asyncio.gather(postgres_pool.close(), redis_pool.close())
