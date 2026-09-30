"""
checks.py — payment-service dependency health checks

Each check function:
  - Is async and lightweight (no writes, no side-effects)
  - Returns a dict with "ok" (bool) and "detail" (str)
  - Catches all exceptions so a failed check never crashes the probe endpoint
  - Times out quickly so /readyz always responds promptly
"""

import asyncio
import logging

import asyncpg
import redis.asyncio as aioredis

from .config import settings

log = logging.getLogger(settings.service_name)


# ---------------------------------------------------------------------------
# PostgreSQL check
# ---------------------------------------------------------------------------

async def check_postgres() -> dict:
    """
    Open a single connection to PostgreSQL, run 'SELECT 1', then close.
    Non-destructive: no data is read or written.
    """
    conn = None
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(settings.payment_db_url),
            timeout=settings.db_connect_timeout,
        )
        await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=settings.db_connect_timeout)
        log.debug("PostgreSQL check passed")
        return {"ok": True, "detail": "reachable"}
    except asyncio.TimeoutError:
        log.warning("PostgreSQL check timed out after %.1fs", settings.db_connect_timeout)
        return {"ok": False, "detail": f"timed out after {settings.db_connect_timeout}s"}
    except Exception as exc:
        log.warning("PostgreSQL check failed: %s", type(exc).__name__)
        return {"ok": False, "detail": type(exc).__name__}
    finally:
        if conn is not None:
            try:
                await asyncio.wait_for(conn.close(), timeout=0.2)
            except Exception:
                conn.terminate()


# ---------------------------------------------------------------------------
# Redis check
# ---------------------------------------------------------------------------

async def check_redis() -> dict:
    """
    Connect to Redis, send PING, then close.
    Non-destructive: only a PING command is issued.
    """
    client = None
    try:
        client = aioredis.from_url(
            settings.payment_redis_url,
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_connect_timeout,
        )
        await asyncio.wait_for(client.ping(), timeout=settings.redis_connect_timeout)
        log.debug("Redis check passed")
        return {"ok": True, "detail": "reachable"}
    except asyncio.TimeoutError:
        log.warning("Redis check timed out after %.1fs", settings.redis_connect_timeout)
        return {"ok": False, "detail": f"timed out after {settings.redis_connect_timeout}s"}
    except Exception as exc:
        log.warning("Redis check failed: %s", type(exc).__name__)
        return {"ok": False, "detail": type(exc).__name__}
    finally:
        if client:
            await client.aclose()


# ---------------------------------------------------------------------------
# Combined readiness check
# ---------------------------------------------------------------------------

async def run_readiness_checks() -> dict:
    """
    Run all dependency checks concurrently and aggregate the result.
    Returns a dict with:
      - ready (bool): True only when ALL checks pass
      - checks (dict): per-dependency results
    """
    postgres_result, redis_result = await asyncio.gather(
        check_postgres(),
        check_redis(),
    )

    checks = {
        "postgres": postgres_result,
        "redis": redis_result,
    }
    all_ok = all(c["ok"] for c in checks.values())

    if all_ok:
        log.info("Readiness probe passed — all dependencies reachable")
    else:
        failed = [name for name, c in checks.items() if not c["ok"]]
        log.warning("Readiness probe failed — unhealthy dependencies: %s", failed)

    return {"ready": all_ok, "checks": checks}
