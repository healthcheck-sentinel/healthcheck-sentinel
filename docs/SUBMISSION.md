# Hackathon submission draft

## Project name
Healthcheck Sentinel

## One-line pitch
Catch services that look alive but cannot serve traffic, then explain the shared dependency failure without flooding Slack.

## Problem
A microservice can return HTTP 200 from a liveness endpoint while its database or cache is unavailable. Basic uptime checks miss this zombie state, and separate service alerts obscure the shared cause.

## Solution
Healthcheck Sentinel polls FastAPI liveness and readiness endpoints, confirms failures through repeated observations, and classifies services as HEALTHY, DEGRADED, ZOMBIE or DOWN. It groups PostgreSQL or Redis failures across payment and order services into one explainable incident. The incident lifecycle produces one active notification and one recovery notification. Prometheus exposes real probe, incident and process-resource measurements.

## How it works
Microservices -> concurrent HTTP probes -> threshold validation -> state classification -> dependency correlation -> incident manager -> ChatOps dispatcher -> Slack. Prometheus collects metrics alongside this flow. The runtime is deterministic Python with no LLM calls.

## Demonstrated results
On the recorded Docker Desktop run, PostgreSQL zombie detection took 5.64 seconds and Redis 7.31 seconds. Agent CPU averaged 0.74% of one logical core over 61.46 seconds between samples. Both dependencies produced one shared incident, one active payload and one recovery payload with no duplicates. Full service shutdown was correctly DOWN, with 14.86-second detection. Fifty-two automated tests passed with 74% aggregate coverage. These are measured results from one environment, not guarantees.

## Technology
Python, FastAPI, asyncio, HTTPX, PostgreSQL, Redis, Docker Compose, Prometheus, pytest and Slack webhook/bot API support. Optional Kubernetes manifests separate readiness from liveness.

## Honest limitations
Real Slack delivery needs workspace credentials; recorded end-to-end notifications currently use a real local HTTP webhook receiver. Incident and deduplication state is in memory. Delivery attempts are at-most-once per transition. Kubernetes manifests are rendered/validated but not cluster-deployed. Remote restart controls are disabled. Brief Docker pause tests can fall between polls; observed transient failure suppression also has deterministic tests.

## AI/tool disclosure
OpenAI Codex assisted with implementation, debugging, test generation and documentation. No AI participates in runtime monitoring or incident decisions.

## Evidence
- docs/FINAL_RESULTS.md: latest verification against the rubric
- docs/submission-validation.json: latest real Docker measurements
- README.md: architecture, setup and operation
- docs/VALIDATION.md: fixes, tests, measured results and limits
- docs/validation-results.json: full run measurements
- docs/validation-before-tuning.json: original higher-CPU result
- docs/demo-smoke.json: final PostgreSQL smoke run

## Fields requiring the submitter
Team/member names, hackathon category, demo video URL, and any platform-specific answers. Confirm the repository is accessible to judges before submitting. Do not claim deployed Kubernetes, real Slack delivery, persistence or authenticated restart actions unless separately completed and verified.
