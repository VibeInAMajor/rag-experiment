#requires -Version 5.1
<#
.SYNOPSIS
Starts only the Workbench-owned TEI deployment with existing local model files.
#>
[CmdletBinding()]
param(
    [string]$ModelDirectory = $env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY,
    [ValidateRange(10, 900)][int]$WaitSeconds = 600,
    [string]$StartupEvidence,
    [switch]$StartOnly
)

$ErrorActionPreference = 'Stop'
$composeFile = Join-Path $PSScriptRoot 'compose.yaml'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$docker = Get-Command docker -CommandType Application -ErrorAction Stop | Select-Object -First 1
if ($StartOnly) {
    $existingId = & $docker.Source ps --all --filter 'name=^/rag-workbench-embedding-1$' --format '{{.ID}}'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the Workbench embedding container.' }
    if ($existingId) {
        $existingState = (& $docker.Source inspect $existingId | ConvertFrom-Json)[0]
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the Workbench embedding container.' }
        if ($existingState.Config.Labels.'com.docker.compose.project' -ne 'rag-workbench-embedding' -or $existingState.Config.Labels.'com.docker.compose.service' -ne 'embedding') {
            throw 'The embedding container name belongs to another deployment. Its owner was not changed.'
        }
        if ($existingState.State.Running) {
            Write-Host 'Embedding: already running; container and model process reused.'
            return
        }
        & $docker.Source start $existingId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Unable to start the existing Workbench embedding container.' }
        Write-Host 'Embedding: started; model loads in the background at http://127.0.0.1:8082/info.'
        return
    }
}
if (-not $ModelDirectory) {
    $localEnvironment = Join-Path $PSScriptRoot '.env'
    if (Test-Path -LiteralPath $localEnvironment -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $localEnvironment) {
            $pair = $line.Split('=', 2)
            if ($pair.Count -eq 2 -and $pair[0] -eq 'WORKBENCH_EMBEDDING_MODEL_DIRECTORY') { $ModelDirectory = $pair[1] }
        }
    }
}
if (-not $ModelDirectory -or -not [IO.Path]::IsPathRooted($ModelDirectory) -or $ModelDirectory.StartsWith('\\') -or $ModelDirectory -match '[\r\n\x00]') {
    throw 'Pass an absolute local model directory with -ModelDirectory.'
}
$modelPath = (Resolve-Path -LiteralPath $ModelDirectory).ProviderPath
foreach ($asset in @('config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors.index.json', 'model-00001-of-00002.safetensors', 'model-00002-of-00002.safetensors')) {
    if (-not (Test-Path -LiteralPath (Join-Path $modelPath $asset) -PathType Leaf)) { throw "Required local model asset is missing: $asset" }
}
if (-not $StartupEvidence) { $StartupEvidence = Join-Path $projectRoot '.cache/workbench-embedding/dedicated-startup.json' }
$evidencePath = [IO.Path]::GetFullPath($StartupEvidence)
$cacheEvidencePath = Join-Path $projectRoot '.cache/workbench-embedding/cache-preparation.json'
$hatch = Get-Command hatch -CommandType Application -ErrorAction Stop | Select-Object -First 1
Push-Location $projectRoot
try {
    & $hatch.Source --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Hatch is unavailable.' }
    & $hatch.Source run workbench-api:python -m scripts.workbench_embedding_cache --model-directory $modelPath --output $cacheEvidencePath
    if ($LASTEXITCODE -ne 0) { throw 'Verified embedding cache preparation failed. Existing model files were preserved.' }
}
finally { Pop-Location }
$cachePreparation = Get-Content -LiteralPath $cacheEvidencePath -Raw | ConvertFrom-Json
$previousDirectory = $env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY
$env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY = $modelPath.Replace('\', '/')
$composeArgs = @('compose', '--project-name', 'rag-workbench-embedding', '-f', $composeFile)
try {
    & $docker.Source @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Workbench embedding Compose configuration.' }
    $containerId = & $docker.Source @composeArgs ps --all --quiet embedding
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the Workbench embedding deployment.' }
    $previousState = $null
    if ($containerId) {
        $previousState = (& $docker.Source inspect $containerId | ConvertFrom-Json)[0]
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the existing Workbench embedding container.' }
    }
    if (-not $containerId) {
        $listener = Get-NetTCPConnection -LocalPort 8082 -State Listen -ErrorAction SilentlyContinue
        if ($listener) { throw 'Port 8082 is occupied. Its owner was not stopped.' }
    }
    $startedAt = [DateTime]::UtcNow
    $timer = [Diagnostics.Stopwatch]::StartNew()
    & $docker.Source @composeArgs up -d embedding
    if ($LASTEXITCODE -ne 0) { throw 'Workbench TEI startup failed. Inspect this deployment with docker compose logs.' }
    if ($StartOnly) {
        Write-Host 'Embedding: created and started; model loads in the background at http://127.0.0.1:8082/info.'
        return
    }
    $samples = @()
    $state = $null
    do {
        $containerId = & $docker.Source @composeArgs ps --all --quiet embedding
        $state = (& $docker.Source inspect $containerId | ConvertFrom-Json)[0]
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the new Workbench embedding container.' }
        if ($state.State.Status -eq 'exited' -or $state.State.Status -eq 'dead' -or $state.RestartCount -gt 0) {
            throw 'Workbench TEI failed during model loading. Inspect its logs; other deployments were not changed.'
        }
        $gpu = & nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
        if ($LASTEXITCODE -eq 0) { $samples += [int]($gpu | Select-Object -First 1) }
        if ($state.State.Health.Status -eq 'healthy') { break }
        Start-Sleep -Milliseconds 500
    } while ($timer.Elapsed.TotalSeconds -lt $WaitSeconds)
    $timer.Stop()
    if ($state.State.Health.Status -ne 'healthy') { throw 'Workbench TEI did not become healthy before the startup deadline.' }
    $info = Invoke-RestMethod -Uri 'http://127.0.0.1:8082/info' -TimeoutSec 5
    if ($info.model_id -ne '/models/5cf2132abc99cad020ac570b19d031efec650f2b' -or $info.auto_truncate -ne $false) {
        throw 'Workbench TEI metadata does not match the selected local model.'
    }
    $newProcess = -not $previousState -or $previousState.State.StartedAt -ne $state.State.StartedAt
    $observedLoading = $newProcess -or $previousState.State.Health.Status -ne 'healthy'
    $readyProbe = $state.State.Health.Log | Where-Object { $_.ExitCode -eq 0 } | Select-Object -First 1
    $readyAt = $(if ($readyProbe) { [DateTimeOffset]::Parse($readyProbe.End) } else { [DateTimeOffset]::UtcNow })
    $startupMs = $(if ($observedLoading) { ($readyAt - [DateTimeOffset]::Parse($state.State.StartedAt)).TotalMilliseconds } else { $null })
    $evidence = [ordered]@{
        project = 'rag-workbench-embedding'
        container_id = $state.Id
        endpoint = 'http://127.0.0.1:8082'
        image_id = $state.Image
        model_directory = $modelPath
        model_cache_volume = $cachePreparation.volume
        cache_mode = $cachePreparation.mode
        cache_preparation_ms = $cachePreparation.preparation_ms
        started_at_utc = $startedAt.ToString('o')
        container_created_at = $state.Created
        container_started_at = $state.State.StartedAt
        restart_count = $state.RestartCount
        new_model_process = $newProcess
        startup_observed_in_progress = $observedLoading
        first_observed_healthy_at = $readyAt.ToString('o')
        launcher_elapsed_ms = $timer.Elapsed.TotalMilliseconds
        startup_to_health_ms = $startupMs
        startup_measurement = $(if ($observedLoading) { 'container process StartedAt through successful Docker health probe; OS cache may be warm' } else { 'existing healthy process; cold startup NOT TESTED' })
        os_file_cache = 'not cleared; may be warm'
        runtime_warm_up = 'TEI may warm up model before health becomes ready'
        inference_requests_sent_by_launcher = 0
        sampled_device_peak_mib = $(if ($samples.Count) { ($samples | Measure-Object -Maximum).Maximum } else { $null })
        gpu_memory_scope = 'shared physical device; separate model process does not reserve exclusive GPU capacity'
        configured_port_bindings = $state.HostConfig.PortBindings
        actual_port_bindings = $state.NetworkSettings.Ports
        compose_project = $state.Config.Labels.'com.docker.compose.project'
        compose_service = $state.Config.Labels.'com.docker.compose.service'
    }
    $null = New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($evidencePath))
    [IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 6) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-Host "Workbench TEI is healthy at http://127.0.0.1:8082; startup evidence: $evidencePath"
}
finally {
    $env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY = $previousDirectory
}
