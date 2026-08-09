param(
  [Parameter(Mandatory)][string]$Repo,
  [int]$Last = 20
)

# Measures the review lane so re-enabling dispatch is an evidence-based decision:
# per merged PR, the AI Review outcome, blocking vs advisory finding counts, and
# request-to-verdict latency when a reviewer was dispatched.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
$prsRaw = & gh pr list --repo $Repo --state merged --limit $Last --json number,title,mergedAt,headRefOid 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prsRaw -join "`n") }
$prs = ($prsRaw -join "`n") | ConvertFrom-Json

$rows = New-Object System.Collections.Generic.List[object]
foreach ($pr in @($prs)) {
  $head = [string]$pr.headRefOid
  $encoded = [uri]::EscapeDataString('AI Review')
  $checkRaw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$head/check-runs?check_name=$encoded" 2>&1
  $conclusion = ''
  if ($LASTEXITCODE -eq 0) {
    $runs = (($checkRaw -join "`n") | ConvertFrom-Json).check_runs
    $latest = @($runs | Where-Object { $_.name -eq 'AI Review' -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
    if ($latest.Count -gt 0) { $conclusion = [string]$latest[0].conclusion }
  }

  $comments = @(Get-Paged "repos/$Repo/issues/$($pr.number)/comments?per_page=100")
  $requests = @($comments | Where-Object {
    (Test-TrustedAutomationComment $_ ([string]$config.owner)) -and [string]$_.body -match "ai-review-request:(?:v\d+:)?(?:codex|copilot):$head"
  } | Sort-Object created_at)
  $verdict = Get-TrustedStructuredCopilotReview -Comments $comments -HeadSha $head -OwnerLogin ([string]$config.owner)
  $latencyMinutes = ''
  if ($requests.Count -gt 0 -and $verdict) {
    $latencyMinutes = [math]::Round((([datetimeoffset]$verdict.created_at) - ([datetimeoffset]$requests[0].created_at)).TotalMinutes, 1)
  }
  $blocking = @($comments | Where-Object { Test-BlockingAiReviewBody ([string]$_.body) }).Count
  $advisory = @($comments | Where-Object { Test-AdvisoryOnlyAiReviewBody ([string]$_.body) }).Count

  $rows.Add([pscustomobject]@{
    pr = [int]$pr.number
    merged_at = [string]$pr.mergedAt
    ai_review = if ($conclusion) { $conclusion } else { 'none' }
    dispatched = ($requests.Count -gt 0)
    latency_min = $latencyMinutes
    blocking_findings = $blocking
    advisory_findings = $advisory
  })
}

$rows | Format-Table -AutoSize | Out-Host
$dispatched = @($rows | Where-Object { $_.dispatched }).Count
Write-Host "REVIEW METRICS: prs=$($rows.Count) dispatched=$dispatched neutral=$(@($rows | Where-Object { $_.ai_review -eq 'neutral' }).Count) blocking_total=$(($rows | Measure-Object -Property blocking_findings -Sum).Sum) advisory_total=$(($rows | Measure-Object -Property advisory_findings -Sum).Sum) dispatch_mode=$($config.independent_review.dispatch_mode)" -ForegroundColor Green
