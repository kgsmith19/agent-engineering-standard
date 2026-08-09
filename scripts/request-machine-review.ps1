param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('auto','codex','copilot')][string]$Provider = 'auto',
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$reviewPolicy = $config.independent_review
if ([string]$reviewPolicy.dispatch_mode -eq 'disabled_pending_e2e') {
  Write-Host 'MACHINE REVIEW DISPATCH DISABLED: dispatch_mode=disabled_pending_e2e; no reviewer is requested until the live E2E canary re-enables dispatch.' -ForegroundColor Yellow
  exit 0
}

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prData = ($prRaw -join "`n") | ConvertFrom-Json
if ([string]$prData.head.repo.full_name -ne $Repo) {
  Write-Host "FORK-DENIED: $Repo PR #$Pr head repository '$([string]$prData.head.repo.full_name)' is not the target repository; no reviewer is requested for fork heads."
  exit 0
}
if ($prData.state -ne 'open') { throw "PR #$Pr is not open." }
if ($prData.draft) { throw "Ready-at-creation policy violation: $Repo PR #$Pr is draft." }

$headSha = [string]$prData.head.sha
$prAuthor = [string]$prData.user.login
$prCommits = @(Get-Paged "repos/$Repo/pulls/$Pr/commits?per_page=100")
$actorLogins = @($prCommits | ForEach-Object { [string]$_.author.login; [string]$_.committer.login } | Where-Object { $_ })
$implementers = @(Get-MachineImplementerProvidersForActors -ActorLogins $actorLogins -PrAuthorLogin $prAuthor)
$acceptedProviders = @(Get-AcceptedMachineReviewProvidersForActors -ActorLogins $actorLogins -PrAuthorLogin $prAuthor)
$preferred = Get-PreferredMachineReviewerForActors -ActorLogins $actorLogins -PrAuthorLogin $prAuthor

$reviews = @(Get-Paged "repos/$Repo/pulls/$Pr/reviews?per_page=100")
$inlineComments = @(Get-Paged "repos/$Repo/pulls/$Pr/comments?per_page=100")
$comments = @(Get-Paged "repos/$Repo/issues/$Pr/comments?per_page=100")
$passes = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]

foreach ($review in $reviews) {
  $reviewProvider = Get-MachineReviewProvider ([string]$review.user.login)
  if (-not $reviewProvider -or $review.commit_id -ne $headSha -or $review.state -in @('DISMISSED','PENDING')) { continue }
  if (Test-BlockingAiReviewEvidence -Body ([string]$review.body) -ReviewState ([string]$review.state)) {
    $failures.Add("$reviewProvider formal review contains blocking findings")
  } elseif ($acceptedProviders -contains $reviewProvider) {
    $passes.Add("$reviewProvider formal review")
  }
}
foreach ($inline in $inlineComments) {
  $inlineProvider = Get-MachineReviewProvider ([string]$inline.user.login)
  if (-not $inlineProvider -or [string]$inline.commit_id -ne $headSha) { continue }
  if (Test-BlockingAiReviewBody ([string]$inline.body)) { $failures.Add("$inlineProvider inline comment #$($inline.id) contains a blocking finding") }
}
$structured = Get-TrustedStructuredCopilotReview -Comments $comments -HeadSha $headSha -OwnerLogin ([string]$config.owner)
if ($structured) {
  if (Test-BlockingAiReviewBody ([string]$structured.body)) { $failures.Add('Copilot structured exact-head review carries a structured threat verdict') }
  elseif ([string]$structured.body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') { }
  elseif ($acceptedProviders -contains 'copilot') { $passes.Add('Copilot structured exact-head PASS') }
}

if ($failures.Count -gt 0) { throw "Current head $headSha has material machine-review findings: $(($failures | Select-Object -Unique) -join '; '). Fix them before requesting another reviewer." }
if ($passes.Count -gt 0) { Write-Host "MACHINE REVIEW ALREADY SATISFIED: $(($passes | Select-Object -Unique) -join '; ') for $headSha" -ForegroundColor Green; exit 0 }

$requestHeads = @{}
foreach ($comment in $comments) {
  if ((Test-TrustedAutomationComment $comment ([string]$config.owner)) -and [string]$comment.body -match 'ai-review-request:(?:v\d+:)?(?:codex|copilot):([0-9a-f]{40})') { $requestHeads[$Matches[1]] = $true }
}
if (-not $requestHeads.ContainsKey($headSha) -and $requestHeads.Count -ge [int]$reviewPolicy.max_review_heads_per_pr) { throw "Machine-review head budget exhausted ($($reviewPolicy.max_review_heads_per_pr))." }

if ($Provider -eq 'auto') {
  $preferredPattern = "ai-review-request:(?:v\d+:)?${preferred}:$headSha"
  $preferredRequest = @($comments | Where-Object { (Test-TrustedAutomationComment $_ ([string]$config.owner)) -and [string]$_.body -match $preferredPattern } | Sort-Object created_at | Select-Object -Last 1)
  if ($preferredRequest.Count -eq 0) { $Provider = $preferred }
  elseif ($preferred -eq 'codex' -and $acceptedProviders -contains 'copilot' -and $reviewPolicy.fallback_provider -eq 'copilot') {
    $age = [datetimeoffset]::UtcNow - [datetimeoffset]$preferredRequest[0].created_at
    $fallbackPattern = "ai-review-request:(?:v\d+:)?copilot:$headSha"
    if ($age.TotalMinutes -ge [int]$reviewPolicy.review_stall_minutes -and @($comments | Where-Object { (Test-TrustedAutomationComment $_ ([string]$config.owner)) -and [string]$_.body -match $fallbackPattern }).Count -eq 0) { $Provider = 'copilot' }
    else { Write-Host "MACHINE REVIEW PENDING: $preferred already requested for $headSha" -ForegroundColor Yellow; exit 0 }
  } else { Write-Host "MACHINE REVIEW PENDING: $preferred already requested for $headSha; no independent fallback is available." -ForegroundColor Yellow; exit 0 }
}

if ($acceptedProviders -notcontains $Provider) { throw "Reviewer '$Provider' is not independent of every recognized implementer in the current PR. Accepted: $($acceptedProviders -join ', ')." }
$marker = "<!-- ai-review-request:v1:${Provider}:$headSha -->"
if (@($comments | Where-Object { (Test-TrustedAutomationComment $_ ([string]$config.owner)) -and [string]$_.body -match "ai-review-request:(?:v\d+:)?${Provider}:$headSha" }).Count -gt 0) { Write-Host "MACHINE REVIEW ALREADY REQUESTED: $Provider for $headSha" -ForegroundColor Yellow; exit 0 }

$verdictContract = "Blocking requires a structured verdict line BLOCK: <CLASS> <file:line> — <concrete exploit precondition>, CLASS one of T1-INFRA-DELETION, T2-BACKDOOR, T3-HARDCODED-SECRET, T4-CRITICAL-VULN. T4-CRITICAL-VULN requires ALL of: introduced by this diff; remotely reachable without authentication; yields RCE, full auth bypass, or cross-tenant data access; concrete input or path cited. When uncertain, file advisory findings instead. Style, quality, architecture, and ordinary bugs are always advisory — P0-P2 prose classifications never block."
$body = if ($Provider -eq 'codex') {
  "@codex review`n`nIndependently review the CURRENT PR head only. You are a fresh reviewer task/session and did not author or commit any code in this PR. Apply one batched pass across: software/security correctness, requirement/spec fit, business/product ROI, systems/operational optimization, and strict leanness/complexity. $verdictContract Do not modify files during review.`n`n$marker"
} else {
  "@copilot Independently review the CURRENT PR head only. You did not author or commit any code in this PR. Do not modify files or push commits during review. Apply software/security, requirement/spec, business/ROI, systems/optimization, and strict leanness lenses. $verdictContract Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $headSha; FAIL is a signal only and blocks nothing without a BLOCK verdict line.`n`n$marker"
}
& gh pr comment $Pr --repo $Repo --body $body | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not request $Provider machine review for $Repo PR #$Pr." }
$implementerText = if ($implementers.Count -gt 0) { $implementers -join '+' } else { 'unknown/human' }
Write-Host "MACHINE REVIEW REQUESTED: provider=$Provider head=$headSha current-PR-implementers=$implementerText" -ForegroundColor Green
