"""Write a bounded local latency lease for payment-service probe endpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / ".sentinel-state" / "state-demo"


def write_lease(mode: str, seconds: int = 45, latency_ms: int = 2000) -> None:
    if mode not in ("degraded", "healthy") or not 1 <= seconds <= 60:
        raise ValueError("Unsupported demo mode or duration")
    if mode == "degraded" and not 500 <= latency_ms <= 5000:
        raise ValueError("Demo latency must be between 500 and 5000 milliseconds")

    DIRECTORY.mkdir(parents=True, exist_ok=True)
    now = time.time()
    lease = {
        "mode": mode,
        "latency_ms": latency_ms,
        "issued_at": now,
        "expires_at": now + seconds if mode == "degraded" else now,
    }
    for stale in DIRECTORY.glob("payment-service*.tmp"):
        try:
            if time.time() - stale.stat().st_mtime > 60:
                stale.unlink()
        except OSError:
            continue

    descriptor, temporary_name = tempfile.mkstemp(prefix="payment-service-", suffix=".tmp", dir=DIRECTORY)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(lease, stream)
            stream.flush()
            os.fsync(stream.fileno())
        target = DIRECTORY / "payment-service.json"
        for attempt in range(5):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass