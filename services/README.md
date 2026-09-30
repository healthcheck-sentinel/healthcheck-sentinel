# services/

This directory contains the FastAPI microservices that make up healthcheck-sentinel.

| Service | Description |
|---|---|
| `health_checker/` | Polls configured endpoints on a schedule and records health status |
| `alert_manager/` | Consumes health events and decides when/how to trigger alerts |
| `api_gateway/` | Unified entry point — aggregates service APIs for clients & dashboards |
