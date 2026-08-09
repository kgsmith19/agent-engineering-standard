param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('auto','codex','copilot')][string]$Provider = 'auto'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
$reviewPolicy = $config.independent_review

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$pr = ($prRaw -join "`n") | ConvertFrom-Json
if ($pr.state -ne 'open') { throw "PR #$Pr is not open." }
if ($pr.draft) { throw "PR #$Pr is draft; machine review is deferred until Ready." }

$headSha = [string]$pr.head.sha
$commitRaw = & gh api "repos/$Repo/commits/$headSha" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($commitRaw -join "`n") }
$commit = ($commitRaw -join "`n") | ConvertFrom-Json
$headAuthor = [string]$commit.author.login
$headCommitter = [string]$commit.committer.login
$prAuthor = [string]$pr.user.login
$acceptedProviders = @(Get-AcceptedMachineReviewProviders `
  -HeadAuthorLogin $headAuthor `
  -HeadCommitterLogin $headCommitter `
  -PrAuthorLogin $prAuthor)
$preferred = Get-PreferredMachineReviewer `
  -HeadAuthorLogin $headAuthor `
  -HeadCommitterLogin $headCommitter `
  -PrAuthorLogin $prAuthor

$reviews = @(Get-Paged "repos/$Repo/pulls/$Pr/reviews?per_page=100")
$inlineComments = @(Get-Paged "repos/$Repo/pulls/$Pr/comments?per_page=100")
$comments = @(Get-Paged "repos/$Repo/issues/$Pr/comments?per_page=100")
$passes = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]

foreach ($review in $reviews) {
  $reviewProvider = Get-MachineReviewProvider -Login ([string]$review.user.login)
  if (-not $reviewProvider -or $review.commit_id -ne $headSha -or $review.state -in @('DISMISSED','PENDING')) { continue }
  if ($review.state -eq 'CHANGES_REQUESTED' -or (Test-MaterialAiReviewBody -Body ([string]$review.body))) {
    $failures.Add("$reviewProvider formal review contains material findings")
  } elseif ($acceptedProviders -contains $reviewProvider) {
    $passes.Add("$reviewProvider formal review")
  }
}
foreach ($inline in $inlineComments) {
  $inlineProvider = Get-MachineReviewProvider -Login ([string]$inline.user.login)
  if (-not $inlineProvider -or [string]$inline.commit_id -ne $headSha) { continue }
  if (Test-MaterialAiReviewBody -Body ([string]$inline.body)) {
    $failures.Add("$inlineProvider inline comment #$($inline.id) contains a material finding")
  }
}

$structured = @($comments | Where-Object {
  (Get-MachineReviewProvider -Login ([string]$_.user.login)) -eq 'copilot' -and
  $_.body -match '(?im)^\s*AI-REVIEW\s+(PASS|FAIL)\b' -and
  $_.body -match [regex]::Escape($headSha)
} | Sort-Object created_at)
if ($structured.Count -gt 0) {
  if ($structured[-1].body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') {
    $failures.Add('Copilot structured exact-head review contains material findings')
  } elseif ($acceptedProviders -contains 'copilot') {
    $passes.Add('Copilot structured exact-head PASS')
  }
}

if ($failures.Count -gt 0) {
  throw "Current head $headSha has material machine-review findings: $(($failures | Select-Object -Unique) -join '; '). Fix them before requesting another reviewer."
}
if ($passes.Count -gt 0) {
  Write-Host "MACHINE REVIEW ALREADY SATISFIED: $(($passes | Select-Object -Unique) -join '; ') for $headSha" -ForegroundColor Green
  exit 0
}

$requestHeads = @{}
foreach ($comment in $comments) {
  if ((Test-TrustedAutomationComment -Comment $comment -OwnerLogin ([string]$config.owner)) -and
      [string]$comment.body -match 'ai-review-request:(?:codex|copilot):([0-9a-f]{40})') { $requestHeads[$Matches[1]] = $true }
}
if (-not $requestHeads.ContainsKey($headSha) -and $requestHeads.Count -ge [int]$reviewPolicy.max_review_heads_per_pr) {
  throw "Machine-review head budget exhausted ($($reviewPolicy.max_review_heads_per_pr))."
}

if ($Provider -eq 'auto') {
  $preferredMarker = "<!-- ai-review-request:${preferred}:$headSha -->"
  $preferredRequest = @($comments | Where-Object {
    (Test-TrustedAutomationComment -Comment $_ -OwnerLogin ([string]$config.owner)) -and [string]$_.body -like "*$preferredMarker*"
  } | Sort-Object created_at | Select-Object -Last 1)
  if ($preferredRequest.Count -eq 0) {
    $Provider = $preferred
  }
  elseif ($preferred -eq 'codex' -and $acceptedProviders -contains 'copilot' -and $reviewPolicy.fallback_provider -eq 'copilot') {
    $age = [datetimeoffset]::UtcNow - [datetimeoffset]$preferredRequest[0].created_at
    $fallbackMarker = "<!-- ai-review-request:copilot:$headSha -->"
    if ($age.TotalMinutes -ge [int]$reviewPolicy.review_stall_minutes -and @($comments | Where-Object {
      (Test-TrustedAutomationComment -Comment $_ -OwnerLogin ([string]$config.owner)) -and [string]$_.body -like "*$fallbackMarker*"
    }).Count -eq 0) {
      $Provider = 'copilot'
    } else {
      Write-Host "MACHINE REVIEW PENDING: $preferred already requested for $headSha" -ForegroundColor Yellow
      exit 0
    }
  }
  else {
    Write-Host "MACHINE REVIEW PENDING: $preferred already requested for $headSha; no independent fallback is available." -ForegroundColor Yellow
    exit 0
  }
}

if ($acceptedProviders -notcontains $Provider) {
  throw "Reviewer '$Provider' is not independent of the latest head implementer. Accepted: $($acceptedProviders -join ', ')."
}

$marker = "<!-- ai-review-request:${Provider}:$headSha -->"
if (@($comments | Where-Object { [string]$_.body -like "*$marker*" }).Count -gt 0) {
  Write-Host "MACHINE REVIEW ALREADY REQUESTED: $Provider for $headSha" -ForegroundColor Yellow
  exit 0
}

switch ($Provider) {
  'codex' {
    $body = "@codex review`n`nIndependently review the CURRENT PR head only. You are a fresh reviewer task/session, not the implementer of this head. Apply one batched pass across: software/security correctness, requirement/spec fit, business/product ROI, systems/operational optimization, and strict leanness/complexity. Report material P0-P2 findings only. Do not modify files during review.`n`n$marker"
  }
  'copilot' {
    $body = "@copilot Independently review the CURRENT PR head only. Do not modify files or push commits during review. Apply software/security, requirement/spec, business/ROI, systems/optimization, and strict leanness lenses. Report material P0-P2 findings only. Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $headSha.`n`n$marker"
  }
}

& gh pr comment $Pr --repo $Repo --body $body | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not request $Provider machine review for $Repo PR #$Pr." }
Write-Host "MACHINE REVIEW REQUESTED: provider=$Provider head=$headSha latest-head-implementer=$(Get-HeadImplementerProvider -HeadAuthorLogin $headAuthor -HeadCommitterLogin $headCommitter -PrAuthorLogin $prAuthor)" -ForegroundColor Green
