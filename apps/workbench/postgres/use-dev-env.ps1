param([switch]$IncludeAdmin)

$ErrorActionPreference = 'Stop'
$dbEnvironmentPath = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $dbEnvironmentPath)) {
    throw 'Generate the local database environment before loading it.'
}

$dbAllowedKeys = @('WORKBENCH_DB_DSN')
if ($IncludeAdmin) {
    $dbAllowedKeys += @('WORKBENCH_DB_ADMIN_PASSWORD', 'WORKBENCH_DB_APP_PASSWORD', 'WORKBENCH_DB_ADMIN_DSN')
}
foreach ($dbLine in Get-Content -LiteralPath $dbEnvironmentPath) {
    if (-not $dbLine -or $dbLine.StartsWith('#')) { continue }
    $dbPair = $dbLine.Split('=', 2)
    if ($dbPair.Count -ne 2 -or $dbPair[0] -notin $dbAllowedKeys) { continue }
    [Environment]::SetEnvironmentVariable($dbPair[0], $dbPair[1], 'Process')
}
if (-not $env:WORKBENCH_DB_DSN) { throw 'The local database application connection is missing.' }
