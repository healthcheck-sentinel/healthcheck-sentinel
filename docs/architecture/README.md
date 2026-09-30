# Architecture

See the root README for the maintained architecture diagram, incident contract, state definitions and deployment workflow. The executable path is services -> agent probes/validator/state manager -> root-cause analyzer -> incident manager -> ChatOps dispatcher -> Slack, with Prometheus metrics alongside it. The empty services/health_checker, services/alert_manager and services/api_gateway packages are historical scaffolding, not additional running services.
