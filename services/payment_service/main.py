"""
payment-service — FastAPI microservice
Handles payment processing simulation.

Ports:
  HTTP: 8001

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
from contextlib import asynccontextmanager
from .checks import close_pools

@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        await close_pools()

app = FastAPI(
    lifespan=lifespan,
    title="Payment Service",
    description="Handles payment processing for healthcheck-sentinel demo.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# In-memory demo store (no real persistence)
# ---------------------------------------------------------------------------
_payments: list[dict] = []


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
        "description": "Handles payment processing",
        "endpoints": ["/", "/healthz", "/readyz", "/payments"],
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


@app.get("/payments", summary="List all demo payments")
async def list_payments():
    """Return the in-memory list of demo payments."""
    log.debug("Listing %d payments", len(_payments))
    return {"payments": _payments, "total": len(_payments)}


@app.post("/payments", summary="Create a demo payment", status_code=201)
async def create_payment(amount: float, currency: str = "USD"):
    """Simulate creating a payment record (no real processing)."""
    payment = {
        "id": str(uuid.uuid4()),
        "amount": amount,
        "currency": currency,
        "status": "success",
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    _payments.append(payment)
    log.info("Payment created: id=%s amount=%s %s", payment["id"], amount, currency)
    return payment


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting %s on port %d", settings.service_name, settings.service_port)
    uvicorn.run("main:app", host="0.0.0.0", port=settings.service_port, reload=True)


# Add resource evidence without changing business endpoints or liveness semantics.
from services.health_resources import ResourceMiddleware
app.add_middleware(ResourceMiddleware)
