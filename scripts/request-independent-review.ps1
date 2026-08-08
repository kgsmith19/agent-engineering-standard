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
$implementer = $null
if ($headRef -match '^agent/(codex|claude|copilot)/') { $implementer = $Matches[1].ToLowerInvariant() }
elseif ($headRef -match '^claude/') { $implementer = 'claude' }
elseif ($headRef -match '^copilot/' -or $author -eq 'Copilot') { $implementer = 'copilot' }
elseif ($author -match '^chatgpt-codex-connector(?:\[bot\])?$') { $implementer = 'codex' }
elseif ($prBody -match '(?im)^\s*Implementer:\s*human\s*$') { $implementer = 'human' }
if (-not $implementer) { throw 'Implementation provenance is unknown; use a controlled agent/<provider>/ branch or declare Implementer: human for human-authored work.' }

$reviewsRaw = & gh api "repos/$Repo/pulls/$Pr/reviews?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($reviewsRaw -join "`n") }
$reviews = @(($reviewsRaw -join "`n") | ConvertFrom-Json)
$currentIndependent = @($reviews | Where-Object {
  $reviewerProvider = Get-ReviewProviderFromLogin -Login $_.user.login
  $_.commit_id -eq $headSha -and $_.state -notin @('DISMISSED','PENDING') -and $reviewerProvider -and (Test-IndependentReview -Implementer $implementer -ReviewerProvider $reviewerProvider)
})
if ($currentIndependent.Count -gt 0) {
  Write-Host "CURRENT-HEAD INDEPENDENT REVIEW ALREADY EXISTS: $($currentIndependent[-1].user.login)" -ForegroundColor Green
  exit 0
}

$commentsRaw = & gh api "repos/$Repo/issues/$Pr/comments?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($commentsRaw -join "`n") }
$comments = @(($commentsRaw -join "`n") | ConvertFrom-Json)
$codexReviews = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'codex' }).Count
$copilotReviews = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'copilot' }).Count
$codexMarker = "<!-- ai-review-request:codex:$headSha -->"
$copilotMarker = "<!-- ai-review-request:copilot:$headSha -->"
$codexOutstanding = @($comments | Where-Object { $_.body -like "*$codexMarker*" }).Count -gt 0
$copilotOutstanding = @($comments | Where-Object { $_.body -like "*$copilotMarker*" }).Count -gt 0

if ($Provider -eq 'auto') {
  $Provider = Get-PreferredIndependentReviewer `
    -Implementer $implementer `
    -CodexAvailable ($codexReviews -lt [int]$reviewPolicy.max_codex_reviews_per_pr -and -not $codexOutstanding) `
    -CopilotAvailable ([bool]$reviewPolicy.copilot_fallback -and $copilotReviews -lt [int]$reviewPolicy.max_copilot_reviews_per_pr -and -not $copilotOutstanding)
}
if (-not (Test-IndependentReview -Implementer $implementer -ReviewerProvider $Provider)) { throw "Reviewer '$Provider' is not independent from implementer '$implementer'." }

switch ($Provider) {
  'codex' {
    if ($codexReviews -ge [int]$reviewPolicy.max_codex_reviews_per_pr) { throw "Codex review-pass budget exhausted for PR #$Pr." }
    if ($codexOutstanding) { throw "Codex review already requested for current head $headSha." }
    & gh pr comment $Pr --repo $Repo --body "@codex review`n`n$codexMarker" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Codex review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Codex pass $($codexReviews + 1)/$($reviewPolicy.max_codex_reviews_per_pr); head=$headSha; implementer=$implementer." -ForegroundColor Green
  }
  'copilot' {
    if ($copilotReviews -ge [int]$reviewPolicy.max_copilot_reviews_per_pr) { throw "Copilot fallback review-pass budget exhausted for PR #$Pr." }
    if ($copilotOutstanding) { throw "Copilot fallback already requested for current head $headSha." }
    $prompt = "@copilot Independently review the CURRENT PR head only. Do not modify files or push commits. Apply software/security, business/product ROI, systems/optimization, and strict leanness lenses. Report only material P0-P2 findings. Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $headSha.`n`n$copilotMarker"
    & gh pr comment $Pr --repo $Repo --body $prompt | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Copilot fallback review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Copilot fallback pass $($copilotReviews + 1)/$($reviewPolicy.max_copilot_reviews_per_pr); head=$headSha; implementer=$implementer." -ForegroundColor Yellow
  }
}
