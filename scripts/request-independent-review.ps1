param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('claude','copilot','codex','human','unknown')][string]$Implementer = 'unknown',
  [ValidateSet('auto','codex','copilot')][string]$Provider = 'auto'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
$reviewPolicy = $config.independent_review

$prRaw = & gh pr view $Pr --repo $Repo --json isDraft,state,headRefOid 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prInfo = ($prRaw -join "`n") | ConvertFrom-Json
if ($prInfo.state -ne 'OPEN') { throw "PR #$Pr is not open." }
if ($prInfo.isDraft) { throw "PR #$Pr is draft. Keep implementation churn in draft; request independent review only when ready." }

$reviewsRaw = & gh api --paginate --slurp "repos/$Repo/pulls/$Pr/reviews?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($reviewsRaw -join "`n") }
$reviewPages = ($reviewsRaw -join "`n") | ConvertFrom-Json
$reviews = @($reviewPages | ForEach-Object { $_ })

$currentIndependent = @(
  $reviews | Where-Object {
    $provider = Get-ReviewProviderFromLogin -Login $_.user.login
    $_.commit_id -eq $prInfo.headRefOid -and
    $provider -and
    (Test-IndependentReview -Implementer $Implementer -ReviewerProvider $provider)
  }
)
if ($currentIndependent.Count -gt 0) {
  Write-Host "CURRENT-HEAD INDEPENDENT REVIEW ALREADY EXISTS: $($currentIndependent[0].user.login)" -ForegroundColor Green
  exit 0
}

$codexReviews = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'codex' }).Count
$copilotReviews = @($reviews | Where-Object { (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'copilot' }).Count

$commentsRaw = & gh api --paginate --slurp "repos/$Repo/issues/$Pr/comments?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($commentsRaw -join "`n") }
$commentPages = ($commentsRaw -join "`n") | ConvertFrom-Json
$comments = @($commentPages | ForEach-Object { $_ })
$codexRequests = @($comments | Where-Object { $_.body -match '(?i)@codex\s+review' }).Count

if ($Provider -eq 'auto') {
  $Provider = Get-PreferredIndependentReviewer `
    -Implementer $Implementer `
    -CodexAvailable (($codexReviews -lt [int]$reviewPolicy.max_codex_reviews_per_pr) -and ($codexRequests -lt [int]$reviewPolicy.max_codex_reviews_per_pr)) `
    -CopilotAvailable ([bool]$reviewPolicy.copilot_fallback -and $copilotReviews -lt [int]$reviewPolicy.max_copilot_reviews_per_pr) `
    -ClaudeAvailable $false
}

if (-not (Test-IndependentReview -Implementer $Implementer -ReviewerProvider $Provider)) {
  throw "Reviewer '$Provider' is not independent from implementer '$Implementer'."
}

switch ($Provider) {
  'codex' {
    if ($codexReviews -ge [int]$reviewPolicy.max_codex_reviews_per_pr -or $codexRequests -ge [int]$reviewPolicy.max_codex_reviews_per_pr) {
      throw "Codex review budget exhausted for PR #$Pr. Use one bounded fallback reviewer instead of repeatedly re-requesting Codex."
    }
    & gh pr comment $Pr --repo $Repo --body '@codex review' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Codex review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Codex GitHub ($($codexRequests + 1)/$($reviewPolicy.max_codex_reviews_per_pr))." -ForegroundColor Green
  }
  'copilot' {
    if ($copilotReviews -ge [int]$reviewPolicy.max_copilot_reviews_per_pr) {
      throw "Copilot review budget exhausted for PR #$Pr. Do not burn another Copilot review without a new explicit justification."
    }
    & gh pr edit $Pr --repo $Repo --add-reviewer '@copilot' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Copilot review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Copilot fallback ($($copilotReviews + 1)/$($reviewPolicy.max_copilot_reviews_per_pr)); review-on-push remains disabled." -ForegroundColor Yellow
  }
}
