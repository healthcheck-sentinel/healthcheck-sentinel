# 🛡️ healthcheck-sentinel

> **Hackathon Project** — An AI-powered health-check monitoring system that watches your services, detects anomalies, and alerts your team through ChatOps integrations.

---

## ✨ Overview

`healthcheck-sentinel` combines **FastAPI microservices**, a **Gemini AI agent**, **Prometheus metrics**, and **Slack/PagerDuty ChatOps** to give you real-time, intelligent alerting for your infrastructure — all deployable on **Kubernetes**.

---

## 🗂️ Project Structure

```
healthcheck-sentinel/
├── services/                  # FastAPI microservices
│   ├── health_checker/        # Polls endpoints & records health status
│   ├── alert_manager/         # Processes & routes alert notifications
│   └── api_gateway/           # Unified API gateway / BFF
├── agent/                     # AI agent (Gemini) for anomaly reasoning
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
| AI Agent | Google Gemini (via `google-generativeai`) |
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
