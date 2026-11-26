#requires -Version 5.1
<#
.SYNOPSIS
Starts the standalone Workbench reranker without enabling application integration.
#>
[CmdletBinding()]
param(
    [string]$ModelDirectory = $env:WORKBENCH_RERANKER_MODEL_DIRECTORY,
    [ValidateRange(10, 900)][int]$WaitSeconds = 600,
    [switch]$StartOnly
)

$ErrorActionPreference = 'Stop'
$docker = (Get-Command docker -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$containerName = 'rag-workbench-reranker-1'
$containerId = & $docker ps --all --filter "name=^/$containerName`$" --format '{{.ID}}'
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the Workbench reranker container. Ensure Docker is running.' }

if ($containerId) {
    $inspection = & $docker inspect $containerId
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the Workbench reranker container.' }
    $state = ($inspection | ConvertFrom-Json)[0]
    if ($state.Config.Labels.'com.docker.compose.project' -ne 'rag-workbench-reranker' -or $state.Config.Labels.'com.docker.compose.service' -ne 'reranker') {
        throw 'The reranker container name belongs to another deployment. Its owner was not changed.'
    }
    if ($state.State.Running) {
        Write-Host 'Reranker: already running; container and model process reused.'
        if ($StartOnly) { return }
    }
    else {
        & $docker start $containerId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Unable to start the existing Workbench reranker container.' }
        Write-Host 'Reranker: started; model loads in the background at http://127.0.0.1:8083/health.'
        if ($StartOnly) { return }
    }
}
else {
    if (-not $ModelDirectory) {
        $localEnvironment = Join-Path $PSScriptRoot '.env'
        if (Test-Path -LiteralPath $localEnvironment -PathType Leaf) {
            foreach ($line in Get-Content -LiteralPath $localEnvironment) {
                $pair = $line.Split('=', 2)
                if ($pair.Count -eq 2 -and $pair[0] -eq 'WORKBENCH_RERANKER_MODEL_DIRECTORY') { $ModelDirectory = $pair[1] }
            }
        }
    }
    if (-not $ModelDirectory -or -not [IO.Path]::IsPathRooted($ModelDirectory) -or $ModelDirectory.StartsWith('\\') -or $ModelDirectory -match '[\r\n\x00]') {
        throw 'Pass an absolute local model directory with -ModelDirectory or configure reranking/.env.'
    }
    $modelPath = (Resolve-Path -LiteralPath $ModelDirectory).ProviderPath
    foreach ($asset in @('config.json', 'tokenizer_config.json', 'chat_template.jinja')) {
        if (-not (Test-Path -LiteralPath (Join-Path $modelPath $asset) -PathType Leaf)) { throw "Required local model asset is missing: $asset" }
    }
    $assetDigests = @{
        'model.safetensors' = '27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b'
        'tokenizer.json' = 'aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4'
    }
    foreach ($asset in $assetDigests.Keys) {
        $digest = Get-FileHash -LiteralPath (Join-Path $modelPath $asset) -Algorithm SHA256
        if ($digest.Hash -ne $assetDigests[$asset]) { throw "Local reranker asset checksum mismatch: $asset" }
    }
    if (Get-NetTCPConnection -LocalPort 8083 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8083 is occupied. Its owner was not stopped.'
    }
    $previousDirectory = $env:WORKBENCH_RERANKER_MODEL_DIRECTORY
    try {
        $env:WORKBENCH_RERANKER_MODEL_DIRECTORY = $modelPath.Replace('\', '/')
        $composeArgs = @('compose', '--project-name', 'rag-workbench-reranker', '-f', (Join-Path $PSScriptRoot 'compose.yaml'))
        & $docker @composeArgs config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Invalid Workbench reranker Compose configuration.' }
        & $docker @composeArgs up -d reranker
        if ($LASTEXITCODE -ne 0) { throw 'Workbench reranker creation failed. Inspect docker compose logs.' }
    }
    finally { $env:WORKBENCH_RERANKER_MODEL_DIRECTORY = $previousDirectory }
    Write-Host 'Reranker: created and started; model loads in the background at http://127.0.0.1:8083/health.'
    if ($StartOnly) { return }
}

$initialRestartCount = if ($containerId) { $state.RestartCount } else { 0 }
$deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
do {
    $inspection = & $docker inspect $containerName
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the Workbench reranker during startup.' }
    $state = ($inspection | ConvertFrom-Json)[0]
    if (-not $state.State.Running -or $state.State.Restarting -or $state.RestartCount -gt $initialRestartCount) {
        throw 'Reranker failed during startup. Inspect docker logs rag-workbench-reranker-1.'
    }
    if ($state.State.Health.Status -eq 'healthy') {
        $models = Invoke-RestMethod -Uri 'http://127.0.0.1:8083/v1/models' -TimeoutSec 5
        if ($models.data.id -notcontains 'Qwen/Qwen3-Reranker-0.6B') { throw 'Reranker serves an unexpected model.' }
        Write-Host 'Reranker: healthy at http://127.0.0.1:8083; application integration remains disabled.'
        return
    }
    Start-Sleep -Seconds 2
} while ([DateTime]::UtcNow -lt $deadline)
throw 'Reranker did not become healthy before the deadline. Inspect docker logs rag-workbench-reranker-1.'
