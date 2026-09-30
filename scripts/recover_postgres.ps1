$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "../docker-compose.yml"
docker compose -f $composeFile start postgres
if ($LASTEXITCODE -ne 0) { throw "Docker start failed for postgres" }
