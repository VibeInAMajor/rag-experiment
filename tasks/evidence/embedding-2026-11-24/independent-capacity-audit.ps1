param(
    [string]$ReportPath = 'tasks/evidence/embedding-2026-11-24/acceptance-capacity.json',
    [string]$OutputPath = 'tasks/evidence/embedding-2026-11-24/independent-capacity-audit.json'
)
$ErrorActionPreference = 'Stop'
$embeddingAudit = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
if ($embeddingAudit.sustainable_tpm_fixed -ne 622592 -or $embeddingAudit.elapsed_seconds -lt 600) {
    throw 'The fixed measured quota or duration does not match the acceptance preflight'
}
$embeddingSnapshot = @($embeddingAudit.events | Where-Object { $_.event -eq 'ledger_snapshot' })[0]
$embeddingStart = [double]$embeddingSnapshot.at
$embeddingEnd = $embeddingStart + $embeddingAudit.elapsed_seconds
$embeddingCharges = @{}
$embeddingViolations = @()
$embeddingPeak = 0
$embeddingPreviousEventTime = [double]::NegativeInfinity
foreach ($embeddingEvent in $embeddingAudit.events) {
    if ($embeddingEvent.at -lt $embeddingPreviousEventTime) { throw 'Event timestamps are not monotonic' }
    $embeddingPreviousEventTime = $embeddingEvent.at
    if ($embeddingEvent.event -eq 'ledger_snapshot') {
        foreach ($embeddingCharge in $embeddingEvent.charges) {
            $embeddingCharges[$embeddingCharge.reservation_id] = $embeddingCharge
        }
    } elseif ($embeddingEvent.event -eq 'reserved') {
        $embeddingCharges[$embeddingEvent.reservation_id] = [pscustomobject]@{
            reserved_at = $embeddingEvent.at
            sent_at = $null
            finished_at = $null
            tokens = $embeddingEvent.tokens
        }
    } elseif ($embeddingEvent.event -eq 'sent') {
        $embeddingCharges[$embeddingEvent.reservation_id].sent_at = $embeddingEvent.at
    } elseif ($embeddingEvent.event -eq 'finished') {
        $embeddingCharges[$embeddingEvent.reservation_id].finished_at = $embeddingEvent.at
    }
    if ($embeddingEvent.event -in @('reserved', 'sent')) {
        $embeddingHeldAndRolling = 0
        foreach ($embeddingCharge in $embeddingCharges.Values) {
            $embeddingChargeTime = if ($null -ne $embeddingCharge.sent_at) { $embeddingCharge.sent_at } else { $embeddingCharge.reserved_at }
            if ($null -eq $embeddingCharge.finished_at -or $embeddingChargeTime -gt $embeddingEvent.at - 60) {
                $embeddingHeldAndRolling += $embeddingCharge.tokens
            }
        }
        $embeddingPeak = [Math]::Max($embeddingPeak, $embeddingHeldAndRolling)
        if ($embeddingHeldAndRolling -gt 591462) {
            $embeddingViolations += @{at=$embeddingEvent.at;tokens=$embeddingHeldAndRolling}
        }
    }
}
$embeddingCompleted = @($embeddingAudit.events | Where-Object {
    $_.event -eq 'finished' -and $_.outcome -eq 'success' -and
    $_.usage_provenance -eq 'provider_reported' -and $_.at -ge $embeddingStart -and $_.at -lt $embeddingEnd
})
$embeddingProviderTokens = ($embeddingCompleted | Measure-Object -Property usage_tokens -Sum).Sum
$embeddingTPM = $embeddingProviderTokens * 60 / $embeddingAudit.elapsed_seconds
$embeddingRatios = @()
for ($embeddingStop = $embeddingStart + 60; $embeddingStop -le $embeddingEnd; $embeddingStop += 1) {
    $embeddingWindowTokens = ($embeddingCompleted | Where-Object {
        $_.at -ge $embeddingStop - 60 -and $_.at -lt $embeddingStop
    } | Measure-Object -Property usage_tokens -Sum).Sum
    $embeddingRatios += $embeddingWindowTokens / 622592
}
$embeddingSorted = @($embeddingRatios | Sort-Object)
$embeddingMiddle = [int][Math]::Floor($embeddingSorted.Count / 2)
$embeddingMedian = if ($embeddingSorted.Count % 2) {
    $embeddingSorted[$embeddingMiddle]
} else {
    ($embeddingSorted[$embeddingMiddle - 1] + $embeddingSorted[$embeddingMiddle]) / 2
}
$embeddingMatchingTotals = $embeddingProviderTokens -eq $embeddingAudit.overall_provider_reported_completed_tokens -and
    [Math]::Abs($embeddingTPM - $embeddingAudit.overall_provider_reported_tpm) -lt 0.000001
$embeddingResult = @{
    status = if ($embeddingMatchingTotals -and $embeddingViolations.Count -eq 0) { 'PASS' } else { 'FAIL' }
    implementation = 'Independent PowerShell replay; no Python governor/evaluator imports'
    scope = 'Accounting consistency and hard-admission replay; the original SLO verdict remains separate'
    original_acceptance_status = $embeddingAudit.status
    sustainable_tpm_fixed = 622592
    hard_budget = 591462
    peak_held_plus_rolling_admitted_tokens = $embeddingPeak
    hard_violations = $embeddingViolations
    elapsed_seconds = $embeddingAudit.elapsed_seconds
    independently_summed_provider_tokens = $embeddingProviderTokens
    independently_computed_tpm = $embeddingTPM
    independently_computed_utilization = $embeddingTPM / 622592
    report_totals_match = $embeddingMatchingTotals
    one_second_window_diagnostic = @{
        window_seconds = 60
        step_seconds = 1
        windows = $embeddingRatios.Count
        median = $embeddingMedian
        band90to95_share = @($embeddingRatios | Where-Object { $_ -ge 0.90 -and $_ -le 0.95 }).Count / $embeddingRatios.Count
        scope = 'Additional diagnostic; original predeclared ten-second-step acceptance rule unchanged'
    }
}
$embeddingResult | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $OutputPath -Encoding utf8
$embeddingResult | ConvertTo-Json -Depth 7
if ($embeddingResult.status -ne 'PASS') { throw 'Independent capacity audit failed' }
