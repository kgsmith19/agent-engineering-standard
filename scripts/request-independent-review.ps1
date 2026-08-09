param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('auto','codex','copilot')][string]$Provider = 'auto'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
$reviewPolicy = $config.independent_review
$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$pr = ($prRaw -join "`n") | ConvertFrom-Json
if ($pr.state -ne 'open') { throw "PR #$Pr is not open." }
if ($pr.draft) { throw "PR #$Pr is draft. Keep implementation churn in draft; request semantic review only when ready." }

$headRef = [string]$pr.head.ref
$headSha = [string]$pr.head.sha
$author = [string]$pr.user.login
$prBody = [string]$pr.body
$implementer = 'unknown'
if ($headRef -match '^agent/(chatgpt|codex|claude|copilot)/') { $implementer = $Matches[1].ToLowerInvariant() }
elseif ($headRef -match '^claude/') { $implementer = 'claude' }
elseif ($headRef -match '^copilot/' -or $author -eq 'Copilot') { $implementer = 'copilot' }
elseif ($author -match '^chatgpt-codex-connector(?:\[bot\])?$') { $implementer = 'codex' }
elseif ($prBody -match '(?im)^\s*Implementer:\s*human\s*$') { $implementer = 'human' }

$requiredProviders = @(Get-RequiredReviewProviders -Implementer $implementer)


$reviewsRaw = & gh api "repos/$Repo/pulls/$Pr/reviews?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($reviewsRaw -join "`n") }
$reviews = @(($reviewsRaw -join "`n") | ConvertFrom-Json)
<<<<<<< HEAD
$currentIndependent = @($reviews | Where-Object {
  $reviewerProvider = Get-ReviewProviderFromLogin -Login $_.user.login
  $_.commit_id -eq $pr.headRefOid -and $_.state -notin @('DISMISSED','PENDING') -and $reviewerProvider -and (Test-IndependentReview -Implementer $implementer -ReviewerProvider $reviewerProvider)
=======
$commentsRaw = & gh api "repos/$Repo/issues/$Pr/comments?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($commentsRaw -join "`n") }
$comments = @(($commentsRaw -join "`n") | ConvertFrom-Json)

$passedCurrent = @{}
foreach ($provider in @('codex','copilot')) {
  $providerReviews = @($reviews | Where-Object {
    (Get-ReviewProviderFromLogin -Login $_.user.login) -eq $provider -and
    $_.commit_id -eq $headSha -and $_.state -notin @('DISMISSED','PENDING')
  } | Sort-Object submitted_at)
  if ($providerReviews.Count -gt 0 -and $providerReviews[-1].state -ne 'CHANGES_REQUESTED') {
    $passedCurrent[$provider] = $true
  }
}

$structuredCopilotResponses = @($comments | Where-Object {
  (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'copilot' -and
  $_.body -match '(?im)^\s*AI-REVIEW\s+(PASS|FAIL)\b'
>>>>>>> origin/main
})
$currentStructuredCopilot = @($structuredCopilotResponses | Where-Object { $_.body -match [regex]::Escape($headSha) } | Sort-Object created_at)
if ($currentStructuredCopilot.Count -gt 0 -and $currentStructuredCopilot[-1].body -match '(?im)^\s*AI-REVIEW\s+PASS\b') {
  $passedCurrent['copilot'] = $true
}

$missing = @($requiredProviders | Where-Object { -not $passedCurrent.ContainsKey($_) })
if ($missing.Count -eq 0) {
  Write-Host "CURRENT-HEAD REQUIRED REVIEWS ALREADY SATISFIED: $($requiredProviders -join ', ')" -ForegroundColor Green
  exit 0
}

<<<<<<< HEAD
$codexReviews = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'codex' }).Count
$copilotReviews = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'copilot' }).Count
$codexRequests = @($comments | Where-Object { $_.body -match '(?i)@codex\s+review' }).Count

if ($Provider -eq 'auto') {
  $Provider = Get-PreferredIndependentReviewer `
    -Implementer $implementer `
    -CodexAvailable (($codexReviews -lt [int]$reviewPolicy.max_codex_reviews_per_pr) -and ($codexRequests -lt [int]$reviewPolicy.max_codex_reviews_per_pr)) `
    -CopilotAvailable ([bool]$reviewPolicy.copilot_fallback -and $copilotReviews -lt [int]$reviewPolicy.max_copilot_reviews_per_pr)
}
if (-not (Test-IndependentReview -Implementer $implementer -ReviewerProvider $Provider)) { throw "Reviewer '$Provider' is not independent from attested implementer '$implementer'." }
=======
# Budgets count actual semantic responses, not duplicate trigger comments.
$codexPassCount = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'codex' }).Count
$copilotFormalCount = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'copilot' }).Count
$copilotStructuredCount = $structuredCopilotResponses.Count
$copilotPassCount = $copilotFormalCount + $copilotStructuredCount

$codexMarker = "<!-- ai-review-request:codex:$headSha -->"
$copilotMarker = "<!-- ai-review-request:copilot:$headSha -->"
$codexOutstanding = @($comments | Where-Object { $_.body -like "*$codexMarker*" }).Count -gt 0
$copilotOutstanding = @($comments | Where-Object { $_.body -like "*$copilotMarker*" }).Count -gt 0

$codexAvailable = ($codexPassCount -lt [int]$reviewPolicy.max_codex_reviews_per_pr) -and -not $codexOutstanding
$copilotAvailable = [bool]$reviewPolicy.copilot_fallback -and ($copilotPassCount -lt [int]$reviewPolicy.max_copilot_reviews_per_pr) -and -not $copilotOutstanding

if ($Provider -eq 'auto') {
  $Provider = $null
  foreach ($candidate in $missing) {
    if ($candidate -eq 'codex' -and $codexAvailable) { $Provider = 'codex'; break }
    if ($candidate -eq 'copilot' -and $copilotAvailable) { $Provider = 'copilot'; break }
  }
  if (-not $Provider) {
    throw "No budgeted required reviewer is available for current head $headSha. Missing: $($missing -join ', '). Codex passes=$codexPassCount/$($reviewPolicy.max_codex_reviews_per_pr), Copilot passes=$copilotPassCount/$($reviewPolicy.max_copilot_reviews_per_pr)."
  }
}
if ($missing -notcontains $Provider) { throw "Reviewer '$Provider' is not a missing required provider for implementer '$implementer'. Missing: $($missing -join ', ')." }
>>>>>>> origin/main

switch ($Provider) {
  'codex' {
    if (-not $codexAvailable) { throw "Codex is unavailable or already requested for current head $headSha." }
    & gh pr comment $Pr --repo $Repo --body "@codex review`n`n$codexMarker" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Codex review for $Repo PR #$Pr." }
<<<<<<< HEAD
    Write-Host "REVIEW REQUESTED: Codex ($($codexRequests + 1)/$($reviewPolicy.max_codex_reviews_per_pr)); attested implementer=$implementer." -ForegroundColor Green
  }
  'copilot' {
    if ($copilotReviews -ge [int]$reviewPolicy.max_copilot_reviews_per_pr) { throw "Copilot review budget exhausted for PR #$Pr." }
    & gh pr edit $Pr --repo $Repo --add-reviewer '@copilot' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Copilot review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Copilot fallback ($($copilotReviews + 1)/$($reviewPolicy.max_copilot_reviews_per_pr)); attested implementer=$implementer." -ForegroundColor Yellow
=======
    Write-Host "REVIEW REQUESTED: Codex response budget $($codexPassCount + 1)/$($reviewPolicy.max_codex_reviews_per_pr); head=$headSha; implementer=$implementer." -ForegroundColor Green
  }
  'copilot' {
    if (-not $copilotAvailable) { throw "Copilot is unavailable or already requested for current head $headSha." }
    $prompt = "@copilot Independently review the CURRENT PR head only. Do not modify files or push commits. Apply software/security, business/product ROI, systems/optimization, and strict leanness lenses. Report only material P0-P2 findings. Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $headSha.`n`n$copilotMarker"
    & gh pr comment $Pr --repo $Repo --body $prompt | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Copilot fallback review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Copilot response budget $($copilotPassCount + 1)/$($reviewPolicy.max_copilot_reviews_per_pr); head=$headSha; implementer=$implementer." -ForegroundColor Yellow
>>>>>>> origin/main
  }
}
