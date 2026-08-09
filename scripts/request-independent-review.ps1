param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('auto','codex','copilot')][string]$Provider = 'auto',
  [switch]$FollowupOnly
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$config = Get-Content (Join-Path $PSScriptRoot '..\policy/github-defaults.json') -Raw | ConvertFrom-Json
$reviewPolicy = $config.independent_review

$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$pr = ($prRaw -join "`n") | ConvertFrom-Json
if ($pr.state -ne 'open') { throw "PR #$Pr is not open." }
if ($pr.draft) { throw "PR #$Pr is draft. Keep implementation churn in draft; request semantic review only when ready." }

$headRef = [string]$pr.head.ref
$headSha = [string]$pr.head.sha
$author = [string]$pr.user.login
$implementer = 'unknown'
if ($headRef -match '^agent/(chatgpt|codex|claude|copilot)/') { $implementer = $Matches[1].ToLowerInvariant() }
elseif ($headRef -match '^claude/') { $implementer = 'claude' }
elseif ($headRef -match '^copilot/' -or $author -eq 'Copilot') { $implementer = 'copilot' }
elseif ($author -match '^chatgpt-codex-connector(?:\[bot\])?$') { $implementer = 'codex' }

$requiredProviders = @(Get-RequiredReviewProviders -Implementer $implementer)

$reviewsRaw = & gh api "repos/$Repo/pulls/$Pr/reviews?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($reviewsRaw -join "`n") }
$reviews = @(($reviewsRaw -join "`n") | ConvertFrom-Json)
$commentsRaw = & gh api "repos/$Repo/issues/$Pr/comments?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($commentsRaw -join "`n") }
$comments = @(($commentsRaw -join "`n") | ConvertFrom-Json)

$passedCurrent = @{}
$failedCurrent = @{}
foreach ($provider in @('codex','copilot')) {
  $providerReviews = @($reviews | Where-Object {
    (Get-ReviewProviderFromLogin -Login $_.user.login) -eq $provider -and
    $_.commit_id -eq $headSha -and $_.state -notin @('DISMISSED','PENDING')
  } | Sort-Object submitted_at)
  if ($providerReviews.Count -gt 0) {
    $latest = $providerReviews[-1]
    if ($latest.state -eq 'CHANGES_REQUESTED') { $failedCurrent[$provider] = $true }
    else { $passedCurrent[$provider] = $true }
  }
}

$structuredCopilotResponses = @($comments | Where-Object {
  (Get-ReviewProviderFromLogin -Login $_.user.login) -eq 'copilot' -and
  $_.body -match '(?im)^\s*AI-REVIEW\s+(PASS|FAIL)\b'
})
$currentStructuredCopilot = @($structuredCopilotResponses | Where-Object {
  $_.body -match [regex]::Escape($headSha)
} | Sort-Object created_at)
if ($currentStructuredCopilot.Count -gt 0) {
  $latestStructured = $currentStructuredCopilot[-1]
  if ($latestStructured.body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') {
    $failedCurrent['copilot'] = $true
    $passedCurrent.Remove('copilot')
  }
  elseif (-not $failedCurrent.ContainsKey('copilot')) {
    $passedCurrent['copilot'] = $true
  }
}

foreach ($requiredProvider in $requiredProviders) {
  if ($failedCurrent.ContainsKey($requiredProvider)) {
    Write-Host "CURRENT-HEAD REQUIRED REVIEW FAILED: $requiredProvider on $headSha. Fix the implementation before spending another provider response." -ForegroundColor Yellow
    exit 0
  }
}

$nextRequiredProvider = Get-NextRequiredReviewProvider `
  -RequiredProviders $requiredProviders `
  -PassedProviders @($passedCurrent.Keys)
if (-not $nextRequiredProvider) {
  Write-Host "CURRENT-HEAD REQUIRED REVIEWS ALREADY SATISFIED: $($requiredProviders -join ', ')" -ForegroundColor Green
  exit 0
}

$passedRequiredCount = @($requiredProviders | Where-Object { $passedCurrent.ContainsKey($_) }).Count
if ($FollowupOnly -and $passedRequiredCount -eq 0) {
  Write-Host "FOLLOW-UP REVIEW NOT NEEDED: no required provider has passed current head $headSha yet."
  exit 0
}

# Count actual semantic responses across the PR. One response is the normal path.
# The hard cap of three preserves a bounded path through legitimate head changes
# without turning every push into an unlimited review loop. Each exact head can
# be requested at most once by the marker checks below.
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
$nextAvailable = if ($nextRequiredProvider -eq 'codex') { $codexAvailable } else { $copilotAvailable }

if ($Provider -eq 'auto') {
  if (-not $nextAvailable) {
    if ($FollowupOnly) {
      Write-Host "FOLLOW-UP REVIEW NOT REQUESTED: ordered next provider '$nextRequiredProvider' is unavailable for head $headSha. Later providers will not be skipped ahead."
      exit 0
    }
    throw "Ordered next required reviewer '$nextRequiredProvider' is unavailable for current head $headSha. Later required providers will not be skipped ahead. Codex responses=$codexPassCount/$($reviewPolicy.max_codex_reviews_per_pr), Copilot responses=$copilotPassCount/$($reviewPolicy.max_copilot_reviews_per_pr). Split/restart the PR rather than violating review order or creating an unbounded loop."
  }
  $Provider = $nextRequiredProvider
}
elseif ($Provider -ne $nextRequiredProvider) {
  throw "Reviewer '$Provider' cannot skip ordered required reviewer '$nextRequiredProvider' for implementer '$implementer'."
}

switch ($Provider) {
  'codex' {
    if (-not $codexAvailable) { throw "Codex is unavailable or already requested for current head $headSha." }
    & gh pr comment $Pr --repo $Repo --body "@codex review`n`n$codexMarker" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Codex review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Codex response budget $($codexPassCount + 1)/$($reviewPolicy.max_codex_reviews_per_pr); head=$headSha; implementer=$implementer." -ForegroundColor Green
  }
  'copilot' {
    if (-not $copilotAvailable) { throw "Copilot is unavailable or already requested for current head $headSha." }
    $prompt = "@copilot Independently review the CURRENT PR head only. Do not modify files or push commits. Apply software/security, business/product ROI, systems/optimization, and strict leanness lenses. Report only material P0-P2 findings. Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $headSha.`n`n$copilotMarker"
    & gh pr comment $Pr --repo $Repo --body $prompt | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not request Copilot fallback review for $Repo PR #$Pr." }
    Write-Host "REVIEW REQUESTED: Copilot response budget $($copilotPassCount + 1)/$($reviewPolicy.max_copilot_reviews_per_pr); head=$headSha; implementer=$implementer." -ForegroundColor Yellow
  }
}
