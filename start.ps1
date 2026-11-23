#requires -Version 5.1
<#
.SYNOPSIS
Starts the local Workbench, API, validator, PostgreSQL and project embedding container.
.DESCRIPTION
Run .\start.ps1 from the repository root. Existing healthy services are reused.
Database setup, migrations and seeding remain explicit operations.
#>
[CmdletBinding()]
param(
    [ValidateSet('', 'api', 'web', 'validator')]
    [string]$Worker = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$scriptPath = $PSCommandPath
$webRoot = Join-Path $projectRoot 'apps/workbench/web'
$logRoot = Join-Path $projectRoot 'output/workbench-services'

function Get-RequiredCommand([string]$Name) {
    $command = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) { throw "Required command '$Name' was not found in PATH." }
    return $command.Source
}

function Test-ServiceResponse([string]$Kind, [string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ne 200) { return $false }
        if ($Kind -eq 'web') { return $response.Content -match '<title>Haystack Workbench</title>' }
        $body = $response.Content | ConvertFrom-Json
        switch ($Kind) {
            'api' { return $body.status -eq 'alive' -and $body.contract_revision -eq 'rag-api-v1.0' }
            'ready' { return $body.status -eq 'ready' -and $body.ready_profile_ids.Count -gt 0 }
            'validator' { return $body.status -eq 'ok' -and $body.validator -eq 'haystack' }
        }
        return $false
    }
    catch { return $false }
}

function Wait-ServiceResponse([string]$Kind, [string]$Url, [int]$Seconds = 60) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        if (Test-ServiceResponse -Kind $Kind -Url $Url) { return $true }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Test-DockerEngine([string]$Executable) {
    try {
        & $Executable info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch { return $false }
}

function Start-LocalPostgres([string]$Executable) {
    $environmentFile = Join-Path $projectRoot 'apps/workbench/postgres/.env'
    if (-not (Test-Path -LiteralPath $environmentFile)) {
        throw 'Database configuration is missing. Complete apps/workbench/api/README.md setup first; existing credentials will not be regenerated.'
    }
    if (-not (Test-DockerEngine -Executable $Executable)) {
        $desktop = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
        if (-not (Test-Path -LiteralPath $desktop)) {
            throw 'Docker is unavailable. Start Docker Desktop and run this script again.'
        }
        Write-Host 'Starting Docker Desktop...'
        Start-Process -FilePath $desktop -WindowStyle Hidden | Out-Null
        $deadline = [DateTime]::UtcNow.AddSeconds(120)
        while (-not (Test-DockerEngine -Executable $Executable)) {
            if ([DateTime]::UtcNow -ge $deadline) { throw 'Docker Desktop did not become ready within 120 seconds.' }
            Start-Sleep -Seconds 2
        }
    }
    $compose = @('compose', '--project-name', 'rag-workbench', '--env-file', $environmentFile, '-f', (Join-Path $projectRoot 'apps/workbench/postgres/compose.yaml'))
    $container = & $Executable @compose ps --all --quiet postgres
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the Workbench PostgreSQL service.' }
    if ($container) {
        $state = & $Executable inspect --format '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' $container
        if ($LASTEXITCODE -eq 0 -and $state -eq 'true healthy') {
            Write-Host 'PostgreSQL: already healthy.'
            return
        }
    }
    Write-Host 'Starting PostgreSQL and waiting for its health check...'
    & $Executable @compose up -d --wait --wait-timeout 90 postgres
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not become healthy. Its existing data volume was preserved.' }
}

function Start-WorkbenchService([hashtable]$Service) {
    if (Test-ServiceResponse -Kind $Service.Kind -Url $Service.Url) {
        Write-Host "$($Service.Name): already running."
        return
    }
    $listener = Get-NetTCPConnection -LocalPort $Service.Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        if (Wait-ServiceResponse -Kind $Service.Kind -Url $Service.Url -Seconds 10) {
            Write-Host "$($Service.Name): already running."
            return
        }
        throw "Port $($Service.Port) is occupied but does not serve a healthy $($Service.Name). No process was stopped."
    }
    if ($Service.Kind -eq 'web') {
        Push-Location $webRoot
        try {
            $npm = Get-RequiredCommand -Name 'npm.cmd'
            if (-not (Test-Path -LiteralPath 'node_modules/vite/bin/vite.js')) {
                Write-Host 'Installing locked frontend dependencies...'
                & $npm ci
                if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
            }
            Write-Host 'Building the frontend...'
            & $npm run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed; the site was not started.' }
        }
        finally { Pop-Location }
    }
    $shell = (Get-Process -Id $PID).Path
    $arguments = @('-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $scriptPath), '-Worker', $Service.Kind)
    $process = Start-Process -FilePath $shell -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logRoot "$($Service.Kind).stdout.log") `
        -RedirectStandardError (Join-Path $logRoot "$($Service.Kind).stderr.log")
    Write-Host "Starting $($Service.Name)..."
    if (-not (Wait-ServiceResponse -Kind $Service.Kind -Url $Service.Url)) {
        throw "$($Service.Name) did not become healthy. Check logs in $logRoot (launcher PID $($process.Id))."
    }
    Write-Host "$($Service.Name): ready."
}

if ($Worker) {
    Push-Location $projectRoot
    try {
        foreach ($secretName in @('WORKBENCH_DB_ADMIN_DSN', 'WORKBENCH_DB_ADMIN_PASSWORD', 'WORKBENCH_DB_APP_PASSWORD', 'WORKBENCH_DB_DSN')) {
            Remove-Item -LiteralPath "Env:$secretName" -ErrorAction SilentlyContinue
        }
        if ($Worker -eq 'web') {
            Set-Location $webRoot
            & (Get-RequiredCommand -Name 'node.exe') 'node_modules/vite/bin/vite.js' preview --host 127.0.0.1 --port 4173 --strictPort
        }
        else {
            $hatch = Get-RequiredCommand -Name 'hatch.exe'
            & $hatch --version
            if ($LASTEXITCODE -ne 0) { throw 'Hatch is unavailable.' }
            if ($Worker -eq 'api') {
                . (Join-Path $projectRoot 'apps/workbench/postgres/use-dev-env.ps1')
                $env:WORKBENCH_API_HOST = '127.0.0.1'
                $env:WORKBENCH_API_PORT = '8011'
                & $hatch run workbench-api:serve
            }
            else { & $hatch -e test run python -m apps.workbench.validator }
        }
        exit $LASTEXITCODE
    }
    finally { Pop-Location }
}

$startupLock = $null
$lockAcquired = $false
Push-Location $projectRoot
try {
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $lockKey = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToUpperInvariant()))).Replace('-', '') }
    finally { $hasher.Dispose() }
    $startupLock = New-Object System.Threading.Mutex($false, "Local\WorkbenchStart_$lockKey")
    try { $lockAcquired = $startupLock.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $lockAcquired = $true }
    if (-not $lockAcquired) { throw 'Workbench startup is already in progress for this project.' }
    $hatch = Get-RequiredCommand -Name 'hatch.exe'
    & $hatch --version
    if ($LASTEXITCODE -ne 0) { throw 'Hatch is unavailable.' }
    $nodeVersion = & (Get-RequiredCommand -Name 'node.exe') --version
    if ($LASTEXITCODE -ne 0 -or [version]$nodeVersion.TrimStart('v') -lt [version]'22.12.0') { throw 'Node.js 22.12.0 or later is required.' }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    Start-LocalPostgres -Executable (Get-RequiredCommand -Name 'docker.exe')
    & (Join-Path $projectRoot 'apps/workbench/embedding/start.ps1') -StartOnly
    foreach ($service in @(
        @{ Name = 'API'; Kind = 'api'; Port = 8011; Url = 'http://127.0.0.1:8011/api/v1/health/live' },
        @{ Name = 'Validator'; Kind = 'validator'; Port = 8010; Url = 'http://127.0.0.1:8010/health' },
        @{ Name = 'Site'; Kind = 'web'; Port = 4173; Url = 'http://127.0.0.1:4173/' }
    )) { Start-WorkbenchService -Service $service }
    if (-not (Wait-ServiceResponse -Kind 'ready' -Url 'http://127.0.0.1:4173/api/v1/health/ready' -Seconds 15)) {
        throw "The site and API are running, but Live readiness is unavailable. Check explicit database setup and logs in $logRoot."
    }
    Write-Host ''
    Write-Host 'Workbench: http://127.0.0.1:4173/'
    Write-Host 'API:       http://127.0.0.1:8011/api/v1/health/ready'
    Write-Host 'Embedding: http://127.0.0.1:8082/info (model readiness is independent of lexical search)'
    Write-Host "Logs:      $logRoot"
}
finally {
    if ($lockAcquired) { $startupLock.ReleaseMutex() }
    if ($startupLock) { $startupLock.Dispose() }
    Pop-Location
}
