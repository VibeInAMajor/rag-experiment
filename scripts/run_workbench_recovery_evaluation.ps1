param([Parameter(Mandatory)][ValidateSet('api', 'database')][string]$Service)

$ErrorActionPreference = 'Stop'
$recoveryRoot = Split-Path -Parent $PSScriptRoot
$recoveryArtifacts = Join-Path $recoveryRoot 'tasks/evidence/eval-vertical-2026-11-22'
$recoveryRunner = Join-Path $PSScriptRoot 'run_workbench_live_evaluation.ps1'
$recoveryBaseline = Get-Content -LiteralPath (Join-Path $recoveryArtifacts 'backend-sql-baseline.json') -Raw | ConvertFrom-Json
$recoveryUtf8 = [System.Text.UTF8Encoding]::new($false)
$recoveryRecord = $null

function Invoke-RecoveryBrowser {
    param([string]$Phase, [string]$Harness = 'resilience', [switch]$SkipRealErrors)
    $recoveryShell = (Get-Process -Id $PID).Path
    $recoveryArguments = @('-NoLogo', '-NoProfile', '-File', $recoveryRunner, '-Phase', $Phase, '-Harness', $Harness)
    if ($Harness -eq 'evaluation') {
        $recoveryArguments += @('-ExpectedCorpusRevision', $recoveryBaseline.corpus_revision)
    }
    if ($SkipRealErrors) { $recoveryArguments += '-SkipRealErrors' }
    & $recoveryShell @recoveryArguments
    if ($LASTEXITCODE -ne 0) { throw "Browser recovery phase '$Phase' failed." }
}

function Save-RecoveryRecord {
    if ($null -ne $recoveryRecord) {
        [System.IO.File]::WriteAllText((Join-Path $recoveryArtifacts "$Service-recovery.json"), ($recoveryRecord | ConvertTo-Json -Depth 8), $recoveryUtf8)
    }
}

function Wait-RecoveryReady {
    $recoveryDeadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $recoveryDeadline) {
        try {
            $recoveryResponse = Invoke-RestMethod 'http://127.0.0.1:8011/api/v1/health/ready' -TimeoutSec 2
            if ($recoveryResponse.status -eq 'ready' -and $recoveryResponse.ready_profile_ids -contains 'postgres-fts-baseline') { return }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    throw 'The existing Live profile did not recover within 60 seconds.'
}

function Read-RecoveryContainer {
    $recoveryContainerIds = @(& docker ps --all --filter 'label=com.docker.compose.project=rag-workbench' --filter 'label=com.docker.compose.service=postgres' --format '{{.ID}}')
    if ($LASTEXITCODE -ne 0 -or $recoveryContainerIds.Count -ne 1) { throw 'Expected exactly one project-owned PostgreSQL container.' }
    $recoveryTemplate = '{"id":{{json .Id}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"started_at":{{json .State.StartedAt}},"mounts":{{json .Mounts}}}'
    $recoveryContainer = (& docker inspect --format $recoveryTemplate $recoveryContainerIds[0]) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $recoveryContainer.project -ne 'rag-workbench' -or $recoveryContainer.service -ne 'postgres') {
        throw 'Refusing to operate on an unverified container.'
    }
    $recoveryVolumeNames = @($recoveryContainer.mounts | Where-Object Type -EQ 'volume' | Select-Object -ExpandProperty Name)
    if ($recoveryVolumeNames.Count -ne 1 -or $recoveryVolumeNames[0] -ne $recoveryBaseline.environment.container.mount_names[0]) {
        throw 'The existing PostgreSQL volume does not match the verified baseline.'
    }
    return [pscustomobject]@{id=$recoveryContainer.id; started_at=$recoveryContainer.started_at; volume=$recoveryVolumeNames[0]}
}

Push-Location $recoveryRoot
try {
    Wait-RecoveryReady
    Invoke-RecoveryBrowser -Phase arm-outage
    $recoveryRecord = [ordered]@{service=$Service; started_at_utc=[DateTime]::UtcNow.ToString('o'); corpus_revision=$recoveryBaseline.corpus_revision; result='RUNNING'}
    if ($Service -eq 'api') {
        $recoveryListeners = @(Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue)
        $recoveryOwners = @($recoveryListeners | Select-Object -ExpandProperty OwningProcess -Unique)
        if ($recoveryOwners.Count -ne 1) { throw 'Expected one API listener owner.' }
        $recoveryOwner = Get-CimInstance Win32_Process -Filter "ProcessId=$($recoveryOwners[0])"
        if ($recoveryOwner.Name -ne 'python.exe' -or $recoveryOwner.CommandLine -notmatch '\s-m\s+apps\.workbench\.api(?:\s|$)') {
            throw 'Refusing to stop a process that is not the known Workbench API.'
        }
        $recoveryRecord.old_api_pid = $recoveryOwner.ProcessId
        Save-RecoveryRecord
        try {
            Stop-Process -Id $recoveryOwner.ProcessId -Force
            Invoke-RecoveryBrowser -Phase api-outage
        } finally {
            & (Join-Path $recoveryRoot 'start.ps1')
            Wait-RecoveryReady
            $recoveryRecord.new_api_pid = (Get-NetTCPConnection -LocalPort 8011 -State Listen | Select-Object -First 1).OwningProcess
            $recoveryRecord.service_restored = $true
            Save-RecoveryRecord
        }
        if ($recoveryRecord.old_api_pid -eq $recoveryRecord.new_api_pid) { throw 'API process identity did not change.' }
        $recoveryPhase = 'after-api'
    } else {
        $recoveryRecord.before = Read-RecoveryContainer
        Save-RecoveryRecord
        try {
            & docker stop --timeout 30 $recoveryRecord.before.id | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL stop failed.' }
            Invoke-RecoveryBrowser -Phase database-outage
            . (Join-Path $recoveryRoot 'apps/workbench/postgres/use-dev-env.ps1')
            & hatch run workbench-api:python -m scripts.workbench_evaluation_probe database-unavailable *> (Join-Path $recoveryArtifacts 'database-unavailable-probe.txt')
            if ($LASTEXITCODE -ne 0) { throw 'Actual database-unavailable API assertions failed.' }
        } finally {
            & docker start $recoveryRecord.before.id | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL start failed; restore the verified existing container.' }
            Wait-RecoveryReady
            $recoveryRecord.service_restored = $true
            Save-RecoveryRecord
        }
        $recoveryRecord.after = Read-RecoveryContainer
        if ($recoveryRecord.before.id -ne $recoveryRecord.after.id -or $recoveryRecord.before.volume -ne $recoveryRecord.after.volume) {
            throw 'Container or volume identity changed during recovery.'
        }
        $recoveryPhase = 'after-database'
    }
    Invoke-RecoveryBrowser -Phase reconnect
    Invoke-RecoveryBrowser -Phase $recoveryPhase -Harness evaluation -SkipRealErrors
    . (Join-Path $recoveryRoot 'apps/workbench/postgres/use-dev-env.ps1')
    & hatch run workbench-api:python -m scripts.workbench_evaluation_probe $recoveryPhase *> (Join-Path $recoveryArtifacts "$recoveryPhase-probe.txt")
    if ($LASTEXITCODE -ne 0) { throw 'Post-restart HTTP/SQL/corpus parity failed.' }
    $recoveryRecord.completed_at_utc = [DateTime]::UtcNow.ToString('o')
    $recoveryRecord.result = 'PASS'
    Save-RecoveryRecord
    $recoveryRecord | ConvertTo-Json -Depth 8
} catch {
    if ($null -ne $recoveryRecord) { $recoveryRecord.result = 'FAIL'; $recoveryRecord.failure_code = 'RECOVERY_EVALUATION_FAILED'; Save-RecoveryRecord }
    throw
}
finally { Pop-Location }
