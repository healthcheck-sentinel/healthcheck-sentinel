# 🛡️ healthcheck-sentinel

> **Hackathon Project** — A deterministic health-check monitoring system that watches your services, tracks state changes, and alerts your team through ChatOps integrations.

---

## ✨ Overview

`healthcheck-sentinel` combines **FastAPI microservices**, a **deterministic monitoring agent**, **Prometheus metrics**, and **Slack/PagerDuty ChatOps** to give you real-time, rule-based alerting for your infrastructure — all deployable on **Kubernetes**.

The monitoring agent is entirely rule-based: it polls endpoints on a schedule, evaluates results against configurable thresholds, tracks state transitions, and emits events. No LLM or generative AI is involved in the runtime path.

---

## 🗂️ Project Structure

```
healthcheck-sentinel/
├── services/                  # FastAPI microservices
│   ├── health_checker/        # Polls endpoints & records health status
│   ├── alert_manager/         # Processes & routes alert notifications
│   └── api_gateway/           # Unified API gateway / BFF
├── agent/                     # Deterministic monitoring agent (poll · evaluate · emit)
├── chatops/                   # Slack & PagerDuty integrations
├── prometheus/                # Prometheus config, alert rules, dashboards
├── kubernetes/                # Kubernetes manifests (Deployments, Services, etc.)
├── tests/                     # Unit, integration, and e2e tests
├── docs/                      # Architecture diagrams, API docs, runbooks
├── .env.example               # Environment variable template
├── .gitignore
└── README.md
```

---

## 🚀 Tech Stack

| Layer | Technology |
|---|---|
| Backend Services | Python · FastAPI · Uvicorn |
| Monitoring Agent | Pure Python · asyncio · rule-based state machine |
| Metrics | Prometheus · Grafana |
| ChatOps | Slack Bolt · PagerDuty Events API v2 |
| Task Queue | Redis · Celery (planned) |
| Database | PostgreSQL + asyncpg |
| Orchestration | Kubernetes · Helm |
| Testing | pytest · httpx · pytest-asyncio |
| CI/CD | GitHub Actions (planned) |

---

## ⚙️ Getting Started

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- `kubectl` (for Kubernetes deployment)

### 1. Clone the repo

```bash
git clone https://github.com/your-org/healthcheck-sentinel.git
cd healthcheck-sentinel
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 3. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r services/requirements.txt
```

### 4. Run locally (coming soon)

```bash
# Services will be wired up with Docker Compose
docker compose up --build
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

---

## 📖 Documentation

See the [`docs/`](docs/) folder for:
- Architecture diagrams
- API reference
- Runbooks & playbooks

---

## 🤝 Contributing

This is a hackathon project — PRs and issues are welcome! Please open an issue first for major changes.

---

## 📄 License

[MIT](LICENSE)
