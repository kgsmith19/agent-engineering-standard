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
  param([Parameter(Mandatory)][string]$Endpoint)
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
$author = [string]$pr.user.login
$reviews = @(Get-Paged "repos/$Repo/pulls/$Pr/reviews?per_page=100")
$comments = @(Get-Paged "repos/$Repo/issues/$Pr/comments?per_page=100")

$currentMachineReviews = @($reviews | Where-Object {
  (Get-MachineReviewProvider -Login ([string]$_.user.login)) -and
  $_.commit_id -eq $headSha -and $_.state -notin @('DISMISSED','PENDING')
})
foreach ($review in $currentMachineReviews) {
  if ($review.state -eq 'CHANGES_REQUESTED' -or (Test-MaterialAiReviewBody -Body ([string]$review.body))) {
    throw "Current head $headSha has material machine-review findings; fix them before requesting another reviewer."
  }
}

$structuredFailures = @($comments | Where-Object {
  (Get-MachineReviewProvider -Login ([string]$_.user.login)) -eq 'copilot' -and
  $_.body -match '(?im)^\s*AI-REVIEW\s+FAIL\b' -and $_.body -match [regex]::Escape($headSha)
})
if ($structuredFailures.Count -gt 0) { throw "Current head $headSha has material Copilot findings; fix them first." }

$preferred = Get-PreferredMachineReviewer -PrAuthorLogin $author
$requestHeads = @{}
foreach ($comment in $comments) {
  if ([string]$comment.body -match 'ai-review-request:(?:codex|copilot):([0-9a-f]{40})') { $requestHeads[$Matches[1]] = $true }
}
if (-not $requestHeads.ContainsKey($headSha) -and $requestHeads.Count -ge [int]$reviewPolicy.max_review_heads_per_pr) {
  throw "Machine-review head budget exhausted ($($reviewPolicy.max_review_heads_per_pr))."
}

if ($Provider -eq 'auto') {
  $preferredMarker = "<!-- ai-review-request:$preferred:$headSha -->"
  $preferredRequest = @($comments | Where-Object { [string]$_.body -like "*$preferredMarker*" } | Sort-Object created_at | Select-Object -Last 1)
  if ($preferredRequest.Count -eq 0) { $Provider = $preferred }
  elseif ($preferred -eq 'codex' -and $reviewPolicy.fallback_provider -eq 'copilot') {
    $age = [datetimeoffset]::UtcNow - [datetimeoffset]$preferredRequest[0].created_at
    $fallbackMarker = "<!-- ai-review-request:copilot:$headSha -->"
    if ($age.TotalMinutes -ge [int]$reviewPolicy.review_stall_minutes -and @($comments | Where-Object { [string]$_.body -like "*$fallbackMarker*" }).Count -eq 0) {
      $Provider = 'copilot'
    } else {
      Write-Host "MACHINE REVIEW PENDING: $preferred already requested for $headSha" -ForegroundColor Yellow
      exit 0
    }
  } else {
    Write-Host "MACHINE REVIEW PENDING: $preferred already requested for $headSha" -ForegroundColor Yellow
    exit 0
  }
}

if ($author.ToLowerInvariant() -match '^chatgpt-codex-connector(?:\[bot\])?$' -and $Provider -eq 'codex') {
  throw 'Codex-authored PRs cannot use Codex as the machine reviewer.'
}

$marker = "<!-- ai-review-request:$Provider:$headSha -->"
if (@($comments | Where-Object { [string]$_.body -like "*$marker*" }).Count -gt 0) {
  Write-Host "MACHINE REVIEW ALREADY REQUESTED: $Provider for $headSha" -ForegroundColor Yellow
  exit 0
}

switch ($Provider) {
  'codex' {
    $body = "@codex review`n`nIndependently review the CURRENT PR head only. You are the reviewer, not the implementer. Apply one batched pass across: software/security correctness, requirement/spec fit, business/product ROI, systems/operational optimization, and strict leanness/complexity. Report material P0-P2 findings only. Do not modify files during review.`n`n$marker"
  }
  'copilot' {
    $body = "@copilot Independently review the CURRENT PR head only. Do not modify files or push commits. Apply software/security, requirement/spec, business/ROI, systems/optimization, and strict leanness lenses. Report material P0-P2 findings only. Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $headSha.`n`n$marker"
  }
}

& gh pr comment $Pr --repo $Repo --body $body | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not request $Provider machine review for $Repo PR #$Pr." }
Write-Host "MACHINE REVIEW REQUESTED: provider=$Provider head=$headSha" -ForegroundColor Green
