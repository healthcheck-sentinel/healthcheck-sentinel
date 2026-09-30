$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "../docker-compose.yml"
docker compose -f $composeFile stop payment-service
if ($LASTEXITCODE -ne 0) { throw "Docker stop failed for payment-service" }
