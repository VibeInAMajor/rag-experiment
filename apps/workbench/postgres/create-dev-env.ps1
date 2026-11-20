$ErrorActionPreference = 'Stop'
$environmentPath = Join-Path $PSScriptRoot '.env'
if (Test-Path -LiteralPath $environmentPath) {
    throw 'Local environment already exists. Preserve its credentials for the existing database volume.'
}

function New-LocalSecret {
    $secretBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    return [Convert]::ToBase64String($secretBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$adminSecret = New-LocalSecret
$applicationSecret = New-LocalSecret
$environmentLines = @(
    "WORKBENCH_DB_ADMIN_PASSWORD=$adminSecret",
    "WORKBENCH_DB_APP_PASSWORD=$applicationSecret",
    "WORKBENCH_DB_ADMIN_DSN=postgresql://workbench_admin:$adminSecret@127.0.0.1:55432/workbench",
    "WORKBENCH_DB_DSN=postgresql://workbench_app:$applicationSecret@127.0.0.1:55432/workbench"
)
Set-Content -LiteralPath $environmentPath -Value $environmentLines -Encoding utf8
Write-Output 'Created the ignored local database environment. Credentials were not printed.'
