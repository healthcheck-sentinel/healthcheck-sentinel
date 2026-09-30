$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "../docker-compose.yml"
docker compose -f $composeFile start payment-service
if ($LASTEXITCODE -ne 0) { throw "Docker start failed for payment-service" }
