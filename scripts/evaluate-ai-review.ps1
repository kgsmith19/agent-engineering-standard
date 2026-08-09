param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
$dispatchDisabled = [string]$config.independent_review.dispatch_mode -eq 'disabled_pending_e2e'

function Invoke-GhJson {
  param([string]$Method,[string]$Endpoint,$Body)
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    $Body | ConvertTo-Json -Depth 10 | Set-Content $tmp -Encoding utf8 -NoNewline
    $raw = & gh api --method $Method $Endpoint --input $tmp 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
    if ($raw) { return (($raw -join "`n") | ConvertFrom-Json) }
  } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

function Set-AiReviewCheck {
  param([string]$HeadSha,[ValidateSet('success','failure','neutral')][string]$Conclusion,[string]$Summary)
  $encoded = [uri]::EscapeDataString('AI Review')
  $raw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$HeadSha/check-runs?check_name=$encoded" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $runs = (($raw -join "`n") | ConvertFrom-Json).check_runs
  $existing = @($runs | Where-Object { $_.name -eq 'AI Review' -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
  $body = @{ status='completed'; conclusion=$Conclusion; output=@{ title='AI Review'; summary=$Summary } }
  if ($existing.Count -gt 0) {
    Invoke-GhJson PATCH "repos/$Repo/check-runs/$($existing[0].id)" $body | Out-Null
  } else {
    $body.name = 'AI Review'; $body.head_sha = $HeadSha
    Invoke-GhJson POST "repos/$Repo/check-runs" $body | Out-Null
  }
}

$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prData = ($prRaw -join "`n") | ConvertFrom-Json
$headSha = [string]$prData.head.sha
$baseSha = [string]$prData.base.sha
# Machine-readable evidence scope: a dispatch_policy_version bump invalidates
# every older neutral/success, so re-enabling dispatch forces fresh evaluation.
$dispatchEvidence = "dispatch-evidence repo=$Repo pr=$Pr head=$headSha base=$baseSha mode=$([string]$config.independent_review.dispatch_mode) policy_version=$([int]$config.independent_review.dispatch_policy_version)"
if ($prData.draft) {
  Set-AiReviewCheck $headSha failure 'Ready-at-creation policy violation: draft PRs are forbidden.'
  exit 0
}

$prAuthor = [string]$prData.user.login
$ownerLogin = [string]$prData.base.repo.owner.login
$prCommits = @(Get-Paged "repos/$Repo/pulls/$Pr/commits?per_page=100")
$actorLogins = @($prCommits | ForEach-Object { [string]$_.author.login; [string]$_.committer.login } | Where-Object { $_ })
$implementers = @(Get-MachineImplementerProvidersForActors -ActorLogins $actorLogins -PrAuthorLogin $prAuthor)
$implementer = if ($implementers.Count -gt 0) { $implementers -join '+' } else { $null }
$acceptedProviders = @(Get-AcceptedMachineReviewProvidersForActors -ActorLogins $actorLogins -PrAuthorLogin $prAuthor)

$reviews = @(Get-Paged "repos/$Repo/pulls/$Pr/reviews?per_page=100")
$inlineComments = @(Get-Paged "repos/$Repo/pulls/$Pr/comments?per_page=100")
$comments = @(Get-Paged "repos/$Repo/issues/$Pr/comments?per_page=100")
$passes = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]

$advisories = New-Object System.Collections.Generic.List[string]

foreach ($review in $reviews) {
  $provider = Get-MachineReviewProvider ([string]$review.user.login)
  if (-not $provider -or $review.commit_id -ne $headSha -or $review.state -in @('DISMISSED','PENDING')) { continue }
  if (Test-BlockingAiReviewEvidence -Body ([string]$review.body) -ReviewState ([string]$review.state)) {
    $failures.Add("$provider review by $($review.user.login) contains blocking P0/P1 findings")
  } else {
    if (Test-AdvisoryAiReviewBody ([string]$review.body)) { $advisories.Add("$provider formal review by $($review.user.login)") }
    if ($acceptedProviders -contains $provider) { $passes.Add("$provider formal review by $($review.user.login)") }
  }
}
foreach ($inline in $inlineComments) {
  $provider = Get-MachineReviewProvider ([string]$inline.user.login)
  if (-not $provider -or [string]$inline.commit_id -ne $headSha) { continue }
  if (Test-BlockingAiReviewBody ([string]$inline.body)) {
    $failures.Add("$provider inline review comment #$($inline.id) contains a blocking current-head finding")
  } elseif (Test-AdvisoryOnlyAiReviewBody ([string]$inline.body)) {
    $advisories.Add("$provider inline review comment #$($inline.id)")
  }
}

$structured = Get-TrustedStructuredCopilotReview -Comments $comments -HeadSha $headSha -OwnerLogin $ownerLogin
if ($structured) {
  if (Test-BlockingAiReviewBody ([string]$structured.body)) {
    $failures.Add('Copilot structured exact-head review contains blocking findings')
  } else {
    if (Test-AdvisoryAiReviewBody ([string]$structured.body)) { $advisories.Add('Copilot structured exact-head review') }
    if ($acceptedProviders -contains 'copilot') { $passes.Add('Copilot structured exact-head PASS') }
  }
}

$codexRequests = @($comments | Where-Object {
  (Test-TrustedAutomationComment $_ $ownerLogin) -and [string]$_.body -like "*ai-review-request:codex:$headSha*"
} | Sort-Object created_at)
foreach ($request in $codexRequests) {
  foreach ($reaction in @(Get-Paged "repos/$Repo/issues/comments/$($request.id)/reactions?per_page=100")) {
    if ((Get-MachineReviewProvider ([string]$reaction.user.login)) -eq 'codex' -and $reaction.content -eq '+1' -and $acceptedProviders -contains 'codex') {
      $passes.Add('Codex thumbs-up on exact-head review request')
    }
  }
}
if ($codexRequests.Count -gt 0 -and $acceptedProviders -contains 'codex') {
  $requestTime = [datetimeoffset]$codexRequests[-1].created_at
  foreach ($reaction in @(Get-Paged "repos/$Repo/issues/$Pr/reactions?per_page=100")) {
    if ((Get-MachineReviewProvider ([string]$reaction.user.login)) -eq 'codex' -and $reaction.content -eq '+1' -and ([datetimeoffset]$reaction.created_at) -ge $requestTime) {
      $passes.Add('Codex PR thumbs-up after exact-head review request')
    }
  }
}

function Ensure-AdvisoryIssue {
  # P2-only findings never block; they are recorded exactly once as a follow-up
  # Issue mapped to this head by a trusted marker comment.
  param([string]$HeadSha,[string[]]$Advisories,$Comments,[string]$OwnerLogin)
  $existing = Get-TrustedAiReviewAdvisoryIssueNumber -Comments $Comments -HeadSha $HeadSha -OwnerLogin $OwnerLogin
  if ($existing) { return [int]$existing }
  $issueBody = "Advisory (P2-only) machine-review findings for ``$Repo`` PR #$Pr at head ``$HeadSha``:`n`n" +
    (@($Advisories | Select-Object -Unique | ForEach-Object { "- $_" }) -join "`n") +
    "`n`nThese findings did not block the merge lane. Address or explicitly discard them."
  $issueRaw = & gh issue create --repo $Repo --title "AI review advisory (P2) follow-ups for PR #$Pr @ $($HeadSha.Substring(0,8))" --body $issueBody 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($issueRaw -join "`n") }
  $issueNumber = [int](([string]($issueRaw -join "`n")) -replace '.*/(\d+)\s*$','$1')
  & gh pr comment $Pr --repo $Repo --body "Recorded P2-only advisory findings as Issue #$issueNumber.`n`n<!-- ai-review-advisory:${HeadSha}:${issueNumber} -->" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Could not record the advisory Issue mapping on $Repo PR #$Pr." }
  return $issueNumber
}

if ($failures.Count -gt 0) {
  Set-AiReviewCheck $headSha failure ("Blocking machine-review finding(s): " + (($failures | Select-Object -Unique) -join '; '))
  exit 0
}
$advisoryNote = ''
if ($advisories.Count -gt 0) {
  $advisoryIssue = Ensure-AdvisoryIssue -HeadSha $headSha -Advisories @($advisories) -Comments $comments -OwnerLogin $ownerLogin
  $advisoryNote = "; P2-only advisory findings recorded in Issue #$advisoryIssue"
}
if ($dispatchDisabled) {
  Set-AiReviewCheck $headSha neutral ("Reviewer dispatch is disabled_pending_e2e; no machine review was solicited for $headSha$advisoryNote`n`n$dispatchEvidence")
  exit 0
}
if ($passes.Count -eq 0) {
  $implementerText = if ($implementer) { $implementer } else { 'unknown/human' }
  Set-AiReviewCheck $headSha failure ("Awaiting exact-head reviewer independent of current-PR implementers=$implementerText. Accepted: " + ($acceptedProviders -join ', '))
  exit 0
}
Set-AiReviewCheck $headSha success ("Exact head $headSha passed machine review; current-PR implementers=$implementer; evidence=" + (($passes | Select-Object -Unique) -join '; ') + $advisoryNote + "`n`n$dispatchEvidence")
