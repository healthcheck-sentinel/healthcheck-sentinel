# Runbooks

Use the named scripts in scripts/ to stop/start PostgreSQL, Redis or payment-service in the local Compose stack. Use scripts/docker_demo.py --full for checked failure/recovery scenarios and measurements. If interrupted, run docker compose start postgres redis payment-service, then inspect http://127.0.0.1:9101/status. See the root README for Slack configuration and the distinction between local HTTP recording and actual Slack delivery.
