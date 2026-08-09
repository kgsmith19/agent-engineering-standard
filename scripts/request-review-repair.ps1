param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
$limit = [int]$config.pr_automation.max_review_fix_attempts

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

function Get-Comments {
  return @(Get-Paged "repos/$Repo/issues/$Pr/comments?per_page=100")
}

function Add-CommentOnce {
  param([string]$Marker,[string]$Body,$Comments)
  if (@($Comments | Where-Object { [string]$_.body -like "*$Marker*" }).Count -gt 0) { return }
  & gh pr comment $Pr --repo $Repo --body "$Body`n`n$Marker" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Could not comment on $Repo PR #$Pr." }
}

function Get-ActiveBlockCodes {
  param($Comments)
  $active = @{}
  foreach ($comment in @($Comments | Sort-Object created_at)) {
    if (-not (Test-TrustedAutomationComment -Comment $comment -OwnerLogin ([string]$config.owner))) { continue }
    $body = [string]$comment.body
    if ($body -match '<!-- automation:block:([a-z0-9-]+):[0-9a-f]{40} -->') { $active[$Matches[1]] = $true }
    elseif ($body -match '<!-- automation:resolve:([a-z0-9-]+):[0-9a-f]{40} -->') { $active.Remove($Matches[1]) }
  }
  return @($active.Keys)
}

function Resolve-TransientReviewBlocks {
  param([string]$Head,$Comments)
  $active = @(Get-ActiveBlockCodes $Comments)
  $resolvedAny = $false
  foreach ($code in @('review-request','review-fallback','review-timeout')) {
    if ($active -notcontains $code) { continue }
    Add-CommentOnce "<!-- automation:resolve:${code}:${Head} -->" 'AUTOMATION-RECOVERED: material review evidence is now being handled by the bounded repair lane.' $Comments
    $resolvedAny = $true
  }
  if (-not $resolvedAny) { return }

  $fresh = @(Get-Comments)
  if (@(Get-ActiveBlockCodes $fresh).Count -eq 0) {
    & gh pr edit $Pr --repo $Repo --remove-label $config.pr_automation.blocked_label 2>&1 | Out-Null
  }
}

$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prData = ($prRaw -join "`n") | ConvertFrom-Json
if ($prData.state -ne 'open' -or $prData.draft) { exit 0 }
$head = [string]$prData.head.sha

$reviews = @(Get-Paged "repos/$Repo/pulls/$Pr/reviews?per_page=100")
$inlineComments = @(Get-Paged "repos/$Repo/pulls/$Pr/comments?per_page=100")
$comments = @(Get-Comments)
$failures = New-Object System.Collections.Generic.List[string]

foreach ($review in $reviews) {
  $provider = Get-MachineReviewProvider -Login ([string]$review.user.login)
  if (-not $provider -or $review.commit_id -ne $head -or $review.state -in @('DISMISSED','PENDING')) { continue }
  if ($review.state -eq 'CHANGES_REQUESTED' -or (Test-MaterialAiReviewBody -Body ([string]$review.body))) {
    $failures.Add("$provider formal review")
  }
}
foreach ($inline in $inlineComments) {
  $provider = Get-MachineReviewProvider -Login ([string]$inline.user.login)
  if (-not $provider -or [string]$inline.commit_id -ne $head) { continue }
  if (Test-MaterialAiReviewBody -Body ([string]$inline.body)) {
    $failures.Add("$provider inline comment #$($inline.id)")
  }
}
foreach ($comment in $comments) {
  if ((Get-MachineReviewProvider -Login ([string]$comment.user.login)) -eq 'copilot' -and
      [string]$comment.body -match '(?im)^\s*AI-REVIEW\s+FAIL\b' -and
      [string]$comment.body -match [regex]::Escape($head)) {
    $failures.Add('Copilot structured review')
  }
}

$attemptedHeads = New-Object System.Collections.Generic.List[string]
foreach ($comment in $comments) {
  if ((Test-TrustedAutomationComment -Comment $comment -OwnerLogin ([string]$config.owner)) -and
      [string]$comment.body -match '<!-- auto-fix:review:([0-9a-f]{40}):\d+ -->' -and -not $attemptedHeads.Contains($Matches[1])) {
    $attemptedHeads.Add($Matches[1])
  }
}
$decision = Get-ReviewRepairDecision `
  -HeadSha $head `
  -AttemptedHeadShas @($attemptedHeads) `
  -MaxAttempts $limit `
  -HasFindings ($failures.Count -gt 0)

switch ($decision) {
  'none' { exit 0 }
  'pending' {
    Write-Host "REVIEW REPAIR PENDING: an agent was already asked to repair current head $head." -ForegroundColor Yellow
    exit 0
  }
  'block' {
    $autoRaw = & gh pr view $Pr --repo $Repo --json autoMergeRequest 2>&1
    if ($LASTEXITCODE -eq 0 -and (($autoRaw -join "`n") | ConvertFrom-Json).autoMergeRequest) {
      & gh pr merge $Pr --repo $Repo --disable-auto 2>&1 | Out-Null
    }
    & gh pr edit $Pr --repo $Repo --add-label $config.pr_automation.blocked_label 2>&1 | Out-Null
    $marker = "<!-- automation:block:review-budget:$head -->"
    $body = "@$($config.owner) AUTOMATION-BLOCKED: the bounded review-repair attempt produced a new head that still has material findings. You are tagged for the decision, never assigned as reviewer."
    Add-CommentOnce $marker $body $comments
    exit 0
  }
  'request' { }
  default { throw "Unexpected review-repair decision '$decision'." }
}

Resolve-TransientReviewBlocks $head $comments
$comments = @(Get-Comments)
$attemptNumber = $attemptedHeads.Count + 1
$marker = "<!-- auto-fix:review:${head}:$attemptNumber -->"
$evidence = (($failures | Select-Object -Unique) -join '; ')
$body = "@copilot address all material machine-review findings on CURRENT head $head ($evidence). Read the full formal and inline review evidence before editing. Follow AGENTS.md and the linked Issue/SPEC. For nontrivial work, create a thin Superpowers-style plan/spec first. Make one batched root-cause fix, never weaken tests/policies/evaluators, verify, and update this existing PR. The new head must pass PR Gate and a different exact-head machine reviewer. Attempt $attemptNumber/$limit."
Add-CommentOnce $marker $body $comments
