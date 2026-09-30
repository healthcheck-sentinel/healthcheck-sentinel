"""
order-service — FastAPI microservice
Handles order management simulation.

Ports:
  HTTP  : 8002
  Metrics: 9102 (future)
"""

from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Order Service",
    description="Manages orders for healthcheck-sentinel demo.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# In-memory state (demo only — no real persistence)
# ---------------------------------------------------------------------------
_orders: list[dict] = []
_ready = True  # flip to False to simulate not-ready state


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Service info")
async def root():
    """Return basic service metadata."""
    return {
        "service": "order-service",
        "version": "0.1.0",
        "port": 8002,
        "description": "Manages customer orders",
        "endpoints": ["/", "/healthz", "/readyz", "/orders"],
    }


@app.get("/healthz", summary="Liveness probe")
async def healthz():
    """
    Liveness probe — confirms the service process is alive.
    Kubernetes will restart the pod if this returns non-2xx.
    """
    return {"status": "ok", "service": "order-service"}


@app.get("/readyz", summary="Readiness probe")
async def readyz():
    """
    Readiness probe — confirms the service is ready to accept traffic.
    Returns 503 if not ready (e.g. warming up, dependency unavailable).
    """
    from fastapi import Response

    if not _ready:
        return Response(
            content='{"status": "not_ready", "service": "order-service"}',
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ready", "service": "order-service"}


@app.get("/orders", summary="List all demo orders")
async def list_orders():
    """Return the in-memory list of demo orders."""
    return {"orders": _orders, "total": len(_orders)}


@app.post("/orders", summary="Create a demo order", status_code=201)
async def create_order(item: str, quantity: int = 1):
    """Simulate placing an order (no real fulfilment logic)."""
    import uuid, datetime

    order = {
        "id": str(uuid.uuid4()),
        "item": item,
        "quantity": quantity,
        "status": "placed",
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    _orders.append(order)
    return order


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
