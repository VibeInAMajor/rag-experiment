param(
    [ValidatePattern('^[a-z0-9_-]{1,32}$')][string]$Phase = 'baseline',
    [ValidatePattern('^[a-z0-9_-]{1,32}$')][string]$Session = 'eval20261122',
    [ValidateSet('evaluation', 'resilience')][string]$Harness = 'evaluation',
    [string]$ExpectedCorpusRevision,
    [switch]$SkipRealErrors,
    [switch]$SkipScreenshots
)

$ErrorActionPreference = 'Stop'
$evaluationRoot = Split-Path -Parent $PSScriptRoot
$evaluationWeb = Join-Path $evaluationRoot 'apps/workbench/web'
$evaluationArtifacts = Join-Path $evaluationRoot 'tasks/evidence/eval-vertical-2026-11-22'
$evaluationWrappers = Join-Path $evaluationRoot 'output/playwright'
$evaluationFixturePath = Join-Path $evaluationRoot 'apps/workbench/retrieval/fixtures/lexical-evaluation.json'
$evaluationHarnessPath = Join-Path $evaluationWeb $(if ($Harness -eq 'evaluation') { 'scripts/live-evaluation-smoke.js' } else { 'scripts/live-resilience-smoke.js' })
New-Item -ItemType Directory -Force -Path $evaluationArtifacts, $evaluationWrappers | Out-Null
$evaluationConfig = @{
    phase = $Phase
    fixture = Get-Content -LiteralPath $evaluationFixturePath -Raw | ConvertFrom-Json
    fixture_sha256 = (Get-FileHash -LiteralPath $evaluationFixturePath -Algorithm SHA256).Hash.ToLowerInvariant()
    expected_corpus_revision = $ExpectedCorpusRevision
    run_real_errors = -not $SkipRealErrors
    capture_screenshots = -not $SkipScreenshots
    sample_state = 'Existing warm API/database; fresh browser page; sequential UI requests; no cache reset.'
}
$evaluationConfigJson = $evaluationConfig | ConvertTo-Json -Depth 12 -Compress
$evaluationHarness = Get-Content -LiteralPath $evaluationHarnessPath -Raw
$evaluationFunction = if ($Harness -eq 'evaluation') { 'liveEvaluationSmoke' } else { 'liveResilienceSmoke' }
$evaluationReportGlobal = if ($Harness -eq 'evaluation') { '__workbenchEvaluationReport' } else { '__workbenchResilienceReport' }
$evaluationWrapper = @"
async function runEvaluation(page) {
  const input = $evaluationConfigJson;
  $evaluationHarness
  try {
    await page.evaluate(value => { window.__workbenchEvaluationInput = value; }, input);
    return await $evaluationFunction(page);
  } catch (error) {
    const saved = await page.evaluate(() => window['$evaluationReportGlobal']).catch(() => null);
    if (saved?.phase === input.phase && saved.result === 'FAIL') return saved;
    return {
      result: 'FAIL',
      phase: input.phase,
      lane: input.phase === 'mock-races' ? 'mock_fault_injection' : 'real-service',
      captured_at_utc: new Date().toISOString(),
      complete_evidence: false,
      failure_code: error.name === 'TimeoutError' ? 'BROWSER_TIMEOUT' : 'BROWSER_HARNESS_FAILED'
    };
  }
}
"@
$evaluationUtf8 = [System.Text.UTF8Encoding]::new($false)
$evaluationWrapperPath = Join-Path $evaluationWrappers "eval-$Phase.js"
[System.IO.File]::WriteAllText($evaluationWrapperPath, $evaluationWrapper, $evaluationUtf8)
Push-Location $evaluationWeb
try {
    $evaluationOutput = & npx --yes --package '@playwright/cli' playwright-cli "-s=$Session" run-code "--filename=$evaluationWrapperPath" 2>&1
    $evaluationExit = $LASTEXITCODE
    $evaluationText = $evaluationOutput -join "`n"
    [System.IO.File]::WriteAllText((Join-Path $evaluationArtifacts "$Phase-browser-cli.txt"), $evaluationText, $evaluationUtf8)
    $evaluationMatch = [regex]::Match($evaluationText, '(?s)### Result\s*\n(?<payload>.*?)\n### Ran Playwright code')
    if ($evaluationExit -ne 0 -or -not $evaluationMatch.Success) {
        $evaluationFailure = [ordered]@{result='FAIL'; phase=$Phase; captured_at_utc=[DateTime]::UtcNow.ToString('o'); complete_evidence=$false; failure_code='BROWSER_CLI_FAILED'}
        [System.IO.File]::WriteAllText((Join-Path $evaluationArtifacts "$Phase-browser.json"), ($evaluationFailure | ConvertTo-Json), $evaluationUtf8)
        throw "Browser phase '$Phase' did not produce a passing report. Inspect $Phase-browser-cli.txt."
    }
    $evaluationReport = $evaluationMatch.Groups['payload'].Value | ConvertFrom-Json
    [System.IO.File]::WriteAllText(
        (Join-Path $evaluationArtifacts "$Phase-browser.json"),
        ($evaluationReport | ConvertTo-Json -Depth 32),
        $evaluationUtf8
    )
    if ($evaluationReport.result -ne 'PASS') { throw "Browser phase '$Phase' failed its acceptance checks." }
    if ($Harness -eq 'resilience') {
        [pscustomobject]@{phase=$Phase; result=$evaluationReport.result; lane=$evaluationReport.lane} | ConvertTo-Json
    } else { [pscustomobject]@{
        phase = $Phase
        result = $evaluationReport.result
        exact_hits = $evaluationReport.summary.exact.expected_source_hits_at_5
        exact_denominator = $evaluationReport.summary.exact.required_cases
        exact_mrr_at_5 = $evaluationReport.summary.exact.mrr_at_5
        paraphrase_hits = $evaluationReport.summary.paraphrase.expected_source_hits_at_5
        paraphrase_denominator = $evaluationReport.summary.paraphrase.required_cases
        corpus_revision = $evaluationReport.service_after.corpus_revision
    } | ConvertTo-Json }
}
finally { Pop-Location }
