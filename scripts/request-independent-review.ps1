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
$prRaw = & gh pr view $Pr --repo $Repo --json isDraft,state,headRefOid,headRefName,author,body 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$pr = ($prRaw -join "`n") | ConvertFrom-Json
if ($pr.state -ne 'OPEN') { throw "PR #$Pr is not open." }
if ($pr.isDraft) { throw "PR #$Pr is draft; semantic review is intentionally deferred." }

$headRef = [string]$pr.headRefName
$author  = [string]$pr.author.login
$prBody  = [string]$pr.body

$implementer = $null
if     ($headRef -match '^agent/(codex|claude|copilot)/') { $implementer = $Matches[1].ToLowerInvariant() }
elseif ($headRef -match '^claude/')                        { $implementer = 'claude' }
elseif ($headRef -match '^copilot/' -or $author -eq 'Copilot') { $implementer = 'copilot' }
elseif ($author -match '^chatgpt-codex-connector(?:\[bot\])?$') { $implementer = 'codex' }
elseif ($prBody -match '(?im)^\s*Implementer:\s*human\s*$') { $implementer = 'human' }

if (-not $implementer) {
  throw "Unknown implementation provenance. Agent PRs must use agent/<provider>/... or a recognized provider branch/author; human PRs must declare 'Implementer: human' in the PR body."
}

$commentsRaw = & gh api "repos/$Repo/issues/$Pr/comments?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($commentsRaw -join "`n") }
$comments = @(($commentsRaw -join "`n") | ConvertFrom-Json)

$reviewsRaw = & gh api "repos/$Repo/pulls/$Pr/reviews?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($reviewsRaw -join "`n") }
$reviews = @(($reviewsRaw -join "`n") | ConvertFrom-Json)
$currentIndependent = @($reviews | Where-Object {
  $reviewerProvider = Get-ReviewProviderFromLogin -Login $_.user.login
  $_.commit_id -eq $pr.headRefOid -and $_.state -notin @('DISMISSED','PENDING') -and $reviewerProvider -and (Test-IndependentReview -Implementer $implementer -ReviewerProvider $reviewerProvider)
})
if ($currentIndependent.Count -gt 0) {
  Write-Host "CURRENT-HEAD INDEPENDENT REVIEW ALREADY EXISTS: $($currentIndependent[-1].user.login)" -ForegroundColor Green
  exit 0
}

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

switch ($Provider) {
  'codex' {
    if ($codexReviews -ge [int]$reviewPolicy.max_codex_reviews_per_pr -or $codexRequests -ge [int]$reviewPolicy.max_codex_reviews_per_pr) { throw "Codex review budget exhausted for PR #$Pr." }
    & gh pr comment $Pr --repo $Repo --body '@codex review' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Codex review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Codex ($($codexRequests + 1)/$($reviewPolicy.max_codex_reviews_per_pr)); attested implementer=$implementer." -ForegroundColor Green
  }
  'copilot' {
    if ($copilotReviews -ge [int]$reviewPolicy.max_copilot_reviews_per_pr) { throw "Copilot review budget exhausted for PR #$Pr." }
    & gh pr edit $Pr --repo $Repo --add-reviewer '@copilot' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Copilot review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Copilot fallback ($($copilotReviews + 1)/$($reviewPolicy.max_copilot_reviews_per_pr)); attested implementer=$implementer." -ForegroundColor Yellow
  }
}
