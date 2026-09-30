"""
payment-service — FastAPI microservice
Handles payment processing simulation.

Ports:
  HTTP  : 8001
  Metrics: 9101 (future)
"""

from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Payment Service",
    description="Handles payment processing for healthcheck-sentinel demo.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# In-memory state (demo only — no real persistence)
# ---------------------------------------------------------------------------
_payments: list[dict] = []
_ready = True  # flip to False to simulate not-ready state


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Service info")
async def root():
    """Return basic service metadata."""
    return {
        "service": "payment-service",
        "version": "0.1.0",
        "port": 8001,
        "description": "Handles payment processing",
        "endpoints": ["/", "/healthz", "/readyz", "/payments"],
    }


@app.get("/healthz", summary="Liveness probe")
async def healthz():
    """
    Liveness probe — confirms the service process is alive.
    Kubernetes will restart the pod if this returns non-2xx.
    """
    return {"status": "ok", "service": "payment-service"}


@app.get("/readyz", summary="Readiness probe")
async def readyz():
    """
    Readiness probe — confirms the service is ready to accept traffic.
    Returns 503 if not ready (e.g. warming up, dependency unavailable).
    """
    from fastapi import Response

    if not _ready:
        return Response(
            content='{"status": "not_ready", "service": "payment-service"}',
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ready", "service": "payment-service"}


@app.get("/payments", summary="List all demo payments")
async def list_payments():
    """Return the in-memory list of demo payments."""
    return {"payments": _payments, "total": len(_payments)}


@app.post("/payments", summary="Create a demo payment", status_code=201)
async def create_payment(amount: float, currency: str = "USD"):
    """Simulate creating a payment record (no real processing)."""
    import uuid, datetime

    payment = {
        "id": str(uuid.uuid4()),
        "amount": amount,
        "currency": currency,
        "status": "success",
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    _payments.append(payment)
    return payment


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
