$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "../docker-compose.yml"
docker compose -f $composeFile start redis
if ($LASTEXITCODE -ne 0) { throw "Docker start failed for redis" }
