"""
user-service — FastAPI microservice
Handles user management simulation.

Ports:
  HTTP  : 8003
  Metrics: 9103 (future)
"""

from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="User Service",
    description="Manages users for healthcheck-sentinel demo.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# In-memory state (demo only — no real persistence)
# ---------------------------------------------------------------------------
_users: list[dict] = [
    # Seed data so the service has something to show immediately
    {"id": "usr-001", "name": "Alice", "email": "alice@example.com", "active": True},
    {"id": "usr-002", "name": "Bob",   "email": "bob@example.com",   "active": True},
]
_ready = True  # flip to False to simulate not-ready state


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Service info")
async def root():
    """Return basic service metadata."""
    return {
        "service": "user-service",
        "version": "0.1.0",
        "port": 8003,
        "description": "Manages user accounts",
        "endpoints": ["/", "/healthz", "/readyz", "/users"],
    }


@app.get("/healthz", summary="Liveness probe")
async def healthz():
    """
    Liveness probe — confirms the service process is alive.
    Kubernetes will restart the pod if this returns non-2xx.
    """
    return {"status": "ok", "service": "user-service"}


@app.get("/readyz", summary="Readiness probe")
async def readyz():
    """
    Readiness probe — confirms the service is ready to accept traffic.
    Returns 503 if not ready (e.g. warming up, dependency unavailable).
    """
    from fastapi import Response

    if not _ready:
        return Response(
            content='{"status": "not_ready", "service": "user-service"}',
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ready", "service": "user-service"}


@app.get("/users", summary="List all demo users")
async def list_users():
    """Return the in-memory list of demo users."""
    return {"users": _users, "total": len(_users)}


@app.post("/users", summary="Create a demo user", status_code=201)
async def create_user(name: str, email: str):
    """Simulate registering a new user (no real auth or persistence)."""
    import uuid

    user = {
        "id": f"usr-{str(uuid.uuid4())[:8]}",
        "name": name,
        "email": email,
        "active": True,
    }
    _users.append(user)
    return user


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)


# Add resource evidence without changing business endpoints or liveness semantics.
from services.health_resources import ResourceMiddleware
app.add_middleware(ResourceMiddleware)
