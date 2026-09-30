"""
order-service — FastAPI microservice
Handles order management simulation.

Ports:
  HTTP: 8002

Health probes:
  GET /healthz  — liveness:  always 200 while the process is alive
  GET /readyz   — readiness: 200 only when PostgreSQL AND Redis are reachable
"""

import logging
import uuid
import datetime

from fastapi import FastAPI, Response
import uvicorn

from .config import settings
from .checks import run_readiness_checks

# ---------------------------------------------------------------------------
# Logging — structured, level driven by env var
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(settings.service_name)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Order Service",
    description="Manages orders for healthcheck-sentinel demo.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# In-memory demo store (no real persistence)
# ---------------------------------------------------------------------------
_orders: list[dict] = []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Service info")
async def root():
    """Return basic service metadata."""
    log.debug("Root endpoint called")
    return {
        "service": settings.service_name,
        "version": "0.1.0",
        "port": settings.service_port,
        "description": "Manages customer orders",
        "endpoints": ["/", "/healthz", "/readyz", "/orders"],
    }


@app.get("/healthz", summary="Liveness probe")
async def healthz():
    """
    Liveness probe — returns 200 as long as the FastAPI process is running.

    This check intentionally does NOT verify external dependencies.
    Kubernetes uses liveness to decide whether to restart the container.
    Restarting on a DB outage would be wrong — use /readyz for that.
    """
    log.debug("Liveness probe called")
    return {"status": "ok", "service": settings.service_name}


@app.get("/readyz", summary="Readiness probe")
async def readyz(response: Response):
    """
    Readiness probe — returns 200 only when ALL critical dependencies are up.

    Checks performed (non-destructive):
      - PostgreSQL: opens a connection, runs SELECT 1, closes connection
      - Redis:      connects and sends PING

    Returns 503 if any dependency is unreachable so the load balancer /
    Kubernetes stops routing traffic to this instance.
    """
    log.info("Readiness probe called")
    result = await run_readiness_checks()

    if not result["ready"]:
        response.status_code = 503  # Service Unavailable

    return {
        "status": "ready" if result["ready"] else "not_ready",
        "service": settings.service_name,
        "checks": result["checks"],
    }


@app.get("/orders", summary="List all demo orders")
async def list_orders():
    """Return the in-memory list of demo orders."""
    log.debug("Listing %d orders", len(_orders))
    return {"orders": _orders, "total": len(_orders)}


@app.post("/orders", summary="Create a demo order", status_code=201)
async def create_order(item: str, quantity: int = 1):
    """Simulate placing an order (no real fulfilment logic)."""
    order = {
        "id": str(uuid.uuid4()),
        "item": item,
        "quantity": quantity,
        "status": "placed",
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    _orders.append(order)
    log.info("Order created: id=%s item=%s qty=%d", order["id"], item, quantity)
    return order


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting %s on port %d", settings.service_name, settings.service_port)
    uvicorn.run("main:app", host="0.0.0.0", port=settings.service_port, reload=True)
