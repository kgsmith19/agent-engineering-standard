param(
  [Parameter(Mandatory)][ValidateSet('pr-event','gate-result','review-event','comment-event','watchdog')][string]$Mode,
  [Parameter(Mandatory)][string]$Repo,
  [int]$Pr = 0,
  [string]$GateConclusion = '',
  [string]$GateHeadSha = '',
  [long]$GateRunId = 0,
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$automation = $config.pr_automation
$reviewPolicy = $config.independent_review
# Deterministic-only merge authority: PR Gate alone is the required context. The
# advisory evaluator runs unconditionally on every gated head — in every
# dispatch_mode and solicit_reviews combination; solicit_reviews gates only
# whether a reviewer is solicited, never whether evaluation happens.
$reviewRequired = [bool]$reviewPolicy.required_for_auto_merge
$reviewSolicit = $reviewRequired -or [bool]$reviewPolicy.solicit_reviews
$dispatchDisabled = [string]$reviewPolicy.dispatch_mode -eq 'disabled_pending_e2e'
$ownerTag = "@$($config.owner)"

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
function Get-Pr {
  param([int]$Number)
  $raw = & gh pr view $Number --repo $Repo --json number,state,isDraft,labels,headRefOid,headRefName,headRepository,headRepositoryOwner,baseRefName,author,autoMergeRequest,mergeable,title,updatedAt 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  return (($raw -join "`n") | ConvertFrom-Json)
}
function Deny-ForkPr {
  # Fail closed before any privileged mutation: fork heads never enter the lane.
  param([int]$Number)
  $prData = Get-Pr $Number
  $headRepo = "$([string]$prData.headRepositoryOwner.login)/$([string]$prData.headRepository.name)"
  if ($headRepo -eq $Repo) { return $false }
  Write-Host "FORK-DENIED: $Repo PR #$Number head repository '$headRepo' is not the target repository; unattended automation refuses cross-repository PRs."
  Set-Blocked $Number 'fork-pr' "Cross-repository (fork) PR from '$headRepo'. Re-home this change into a branch of the managed repository; the unattended lane never runs privileged automation for fork heads." $prData
  return $true
}
function Get-Comments { param([int]$Number) return @(Get-Paged "repos/$Repo/issues/$Number/comments?per_page=100") }
function Add-CommentOnce {
  # MatchPattern lets writers emit versioned markers while deduplicating against
  # both versioned and legacy unversioned forms.
  param([int]$Number,[string]$Marker,[string]$Body,[string]$MatchPattern = '')
  if (-not $MatchPattern) { $MatchPattern = [regex]::Escape($Marker) }
  if (@(Get-Comments $Number | Where-Object { (Test-TrustedAutomationComment $_ ([string]$config.owner)) -and [string]$_.body -match $MatchPattern }).Count -gt 0) { return }
  & gh pr comment $Number --repo $Repo --body "$Body`n`n$Marker" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Could not comment on $Repo PR #$Number." }
}
function Disable-AutoMerge {
  param([int]$Number,$PrData)
  if (-not $PrData.autoMergeRequest) { return }
  $raw = & gh pr merge $Number --repo $Repo --disable-auto 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
}
function Get-ActiveBlockCodes {
  param([int]$Number)
  $active = @{}
  foreach ($comment in @(Get-Comments $Number | Sort-Object created_at)) {
    if (-not (Test-TrustedAutomationComment $comment ([string]$config.owner))) { continue }
    $body = [string]$comment.body
    if ($body -match '<!-- automation:(?:v\d+:)?block:([a-z0-9-]+):[0-9a-f]{40} -->') { $active[$Matches[1]] = $true }
    elseif ($body -match '<!-- automation:(?:v\d+:)?resolve:([a-z0-9-]+):[0-9a-f]{40} -->') { $active.Remove($Matches[1]) }
  }
  return @($active.Keys)
}
function Get-BlockAdvice {
  # Machine-actionable next step per block code (FR-9); the marker comment stays
  # the machine handle, this prose is for the human/agent reading the PR.
  param([string]$Code)
  $advice = @{
    'draft-pr'='mark the PR Ready (agents must create PRs with draft:false); automation re-evaluates on the ready_for_review event.'
    'copilot-owned-pr'='re-home this change into a non-Copilot branch and PR; GitHub requires human review and merge for Copilot-owned PRs.'
    'fork-pr'='push the same change to a branch inside this repository and open a PR from it; fork heads never enter the unattended lane.'
    'risk-labels'='leave exactly one risk:R0..R4 label on the PR; the block resolves on the next event.'
    'ci-budget'='fix the failing gate manually (the bounded repair budget is spent) and push; the block clears on the next gate success.'
    'conflict-budget'='resolve the merge conflict manually and push; the block clears when the head stops conflicting.'
    'review-budget'='address the review findings manually and push a new head; the reviewed-head budget is spent.'
    'ci-dispatch-disabled'='fix CI manually, or wait for dispatch to be enabled — the bounded repair lane then resumes and clears this block.'
    'conflict-dispatch-disabled'='resolve the conflict manually, or wait for dispatch to be enabled — the repair lane then resumes and clears this block.'
    'review-dispatch-disabled'='wait for dispatch to be enabled; the bounded review-repair lane resumes automatically.'
    'auto-merge-settings'='reconcile live settings and ruleset — run the "Ops: Portfolio Bootstrap" workflow once AUTOMATION_TOKEN is provisioned, or scripts/setup-portfolio.ps1 locally — then any PR event re-arms.'
    'automation-identity-missing'='provision the AUTOMATION_TOKEN / GH_TOKEN_ADMIN secret (owner authority); promotion retries on the next event.'
    'review-request'='check reviewer connectivity and budgets, then re-trigger with a review event or wait for the watchdog.'
    'review-fallback'='no independent fallback reviewer exists for this head; wait for the primary reviewer or adjust provider connectivity.'
    'review-timeout'='the reviewer exceeded the absolute timeout; a later valid review event still recovers this PR automatically.'
    'missing-pr-gate'='make the deterministic gate workflow trigger for this PR (check workflow name and trigger types), then push or re-run it.'
    'workflow-approval'='disable the Copilot cloud-agent workflow-approval setting for this repository (one-time UI step), then re-run the gate.'
    'gate-skipped'='fix the gate workflow trigger or job condition so a Ready PR always runs it, then push.'
  }
  if ($advice.ContainsKey($Code)) { return [string]$advice[$Code] }
  return 'inspect the reason above, fix the underlying condition, and the next PR event re-evaluates.'
}
function Set-Blocked {
  param([int]$Number,[string]$Code,[string]$Reason,$PrData)
  if (-not $PrData) { $PrData = Get-Pr $Number }
  Disable-AutoMerge $Number $PrData
  & gh pr edit $Number --repo $Repo --add-label $automation.blocked_label 2>&1 | Out-Null
  $head = [string]$PrData.headRefOid
  # While dispatch is disabled no comment @-mentions a human; the owner is named.
  $ownerReference = if ($dispatchDisabled) { "the owner ($($config.owner))" } else { $ownerTag }
  $body = "Automation put this PR on hold ($Code): $Reason`n`nNext step: $(Get-BlockAdvice $Code)`n`nDecision contact: $ownerReference — named for the decision, never assigned as a reviewer."
  Add-CommentOnce $Number "<!-- automation:v1:block:${Code}:${head} -->" $body "<!-- automation:(?:v\d+:)?block:${Code}:${head} -->"
}
function Resolve-Block {
  param([int]$Number,[string]$Code,[string]$Evidence,$PrData)
  if (-not $PrData) { $PrData = Get-Pr $Number }
  if (@(Get-ActiveBlockCodes $Number) -notcontains $Code) { return }
  $head = [string]$PrData.headRefOid
  Add-CommentOnce $Number "<!-- automation:v1:resolve:${Code}:${head} -->" "AUTOMATION-RECOVERED: $Evidence" "<!-- automation:(?:v\d+:)?resolve:${Code}:${head} -->"
  if (@(Get-ActiveBlockCodes $Number).Count -eq 0) { & gh pr edit $Number --repo $Repo --remove-label $automation.blocked_label 2>&1 | Out-Null }
}
function Remove-ForbiddenReviewers {
  param([int]$Number)
  $raw = & gh api "repos/$Repo/pulls/$Number/requested_reviewers" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $requested = @(($raw -join "`n") | ConvertFrom-Json | Select-Object -ExpandProperty users | ForEach-Object { [string]$_.login })
  $forbidden = @($config.forbidden_requested_reviewers | Where-Object { $requested -contains [string]$_ })
  if ($forbidden.Count -eq 0) { return }
  Invoke-GhJson DELETE "repos/$Repo/pulls/$Number/requested_reviewers" @{ reviewers=$forbidden; team_reviewers=@() } | Out-Null
  $ownerReference = if ($dispatchDisabled) { "the owner ($($config.owner))" } else { $ownerTag }
  Add-CommentOnce $Number '<!-- automation:v1:removed-reviewers -->' "Removed forbidden requested reviewer(s): $($forbidden -join ', '). Routine automation may tag $ownerReference for authority, but never assigns Kyle as a reviewer." '<!-- automation:(?:v\d+:)?removed-reviewers -->'
}
function Tag-Authority {
  param([int]$Number,[ValidateSet('control_plane','R4')][string]$Kind)
  $gate = $config.manual_gates.PSObject.Properties[$Kind].Value
  # While dispatch is disabled no comment @-mentions a human; the owner is named.
  $header = if ($dispatchDisabled) { "Authority needed from the owner ($($config.owner)) — $Kind" } else { "$ownerTag — authority needed: $Kind" }
  $trailer = if ($dispatchDisabled) { 'Next step: review the evidence above and decide. All machine checks still run; the owner is named without an @-mention while dispatch is disabled and never assigned as a GitHub reviewer.' } else { 'Next step: review the evidence above and decide. All machine checks still run; you are tagged, never assigned as a GitHub reviewer.' }
  $body = @"
$header

- Failure class prevented: $($gate.failure_class_prevented)
- Why automation is insufficient: $($gate.why_automation_is_insufficient)
- Decision owner: $($gate.decision_owner)
- Gate removal condition: $($gate.gate_removal_condition)

$trailer
"@
  Add-CommentOnce $Number "<!-- authority-required:v1:$Kind -->" $body "<!-- authority-required:(?:v\d+:)?$Kind -->"
}
function Get-ChangedFiles {
  param([int]$Number)
  $raw = & gh api --paginate "repos/$Repo/pulls/$Number/files?per_page=100" --jq '.[].filename' 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  return @($raw | Where-Object { $_ })
}
function Test-ControlPlane {
  param([int]$Number)
  if ($Repo -match '/agent-engineering-standard$') { return $true }
  foreach ($path in @(Get-ChangedFiles $Number)) { if (Test-ControlPlanePath $path) { return $true } }
  return $false
}
function Get-Risk { param($PrData) return Get-RiskFromLabels @($PrData.labels | ForEach-Object { $_.name }) }

function Request-Repair {
  param([ValidateSet('ci','review','conflict')][string]$Kind,[int]$Number,$PrData,[long]$RunId = 0)
  if ($dispatchDisabled) {
    # No outbound agent tag (@copilot/@dependabot) leaves the repo while dispatch
    # is disabled; the block is machine-readable and recovers when dispatch enables.
    Set-Blocked $Number "$Kind-dispatch-disabled" "Agent dispatch is disabled_pending_e2e, so the bounded $Kind repair lane posts no agent request. This block clears automatically once dispatch is enabled and the lane resumes." $PrData
    return
  }
  Resolve-Block $Number "$Kind-dispatch-disabled" "Agent dispatch is enabled; the bounded $Kind repair lane resumed." $PrData
  $limits = @{ ci=[int]$automation.max_ci_fix_attempts; review=[int]$automation.max_review_fix_attempts; conflict=[int]$automation.max_conflict_fix_attempts }
  $comments = @(Get-Comments $Number)
  $attempts = @($comments | Where-Object { (Test-TrustedAutomationComment $_ ([string]$config.owner)) -and [string]$_.body -match "<!-- auto-fix:(?:v\d+:)?${Kind}:" }).Count
  if ($attempts -ge $limits[$Kind]) { Set-Blocked $Number "$Kind-budget" "$Kind repair budget exhausted ($($limits[$Kind]) )." $PrData; return }
  $head = [string]$PrData.headRefOid
  $marker = "<!-- auto-fix:v1:${Kind}:${head}:$($attempts + 1) -->"
  $markerPattern = "<!-- auto-fix:(?:v\d+:)?${Kind}:${head}:$($attempts + 1) -->"
  if ($Kind -eq 'conflict' -and [string]$PrData.author.login -eq 'dependabot[bot]') { Add-CommentOnce $Number $marker '@dependabot rebase' $markerPattern; return }
  $scope = switch ($Kind) {
    'ci' { if ($RunId) { "GitHub Actions run $RunId" } else { 'the current failing PR Gate' } }
    'review' { "material current-head AI review findings for $head" }
    'conflict' { 'the merge conflict against current main' }
  }
  $body = "@copilot investigate and fix $scope on PR #$Number. Read the complete evidence before editing. Follow AGENTS.md and the linked Issue/SPEC. For nontrivial or cross-cutting work, create a thin Superpowers-style plan/spec first. Make the smallest root-cause fix, never weaken tests/policies/evaluators, verify, and update this existing PR. Attempt $($attempts + 1)/$($limits[$Kind])."
  Add-CommentOnce $Number $marker $body $markerPattern
}

function Get-ReviewFailures {
  param([int]$Number,$PrData)
  $head = [string]$PrData.headRefOid
  $failures = New-Object System.Collections.Generic.List[string]
  foreach ($review in @(Get-Paged "repos/$Repo/pulls/$Number/reviews?per_page=100")) {
    $provider = Get-MachineReviewProvider ([string]$review.user.login)
    if (-not $provider -or $review.commit_id -ne $head -or $review.state -in @('DISMISSED','PENDING')) { continue }
    if (Test-BlockingAiReviewEvidence -Body ([string]$review.body) -ReviewState ([string]$review.state)) { $failures.Add($provider) }
  }
  foreach ($inline in @(Get-Paged "repos/$Repo/pulls/$Number/comments?per_page=100")) {
    $provider = Get-MachineReviewProvider ([string]$inline.user.login)
    if (-not $provider -or [string]$inline.commit_id -ne $head) { continue }
    if (Test-BlockingAiReviewBody ([string]$inline.body)) { $failures.Add($provider) }
  }
  $comments = @(Get-Comments $Number)
  $structured = Get-TrustedStructuredCopilotReview -Comments $comments -HeadSha $head -OwnerLogin ([string]$config.owner)
  if ($structured -and (Test-BlockingAiReviewBody ([string]$structured.body))) { $failures.Add('copilot') }
  return @($failures | Select-Object -Unique)
}
function Invoke-AiReview {
  param([int]$Number)
  & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'evaluate-ai-review.ps1') -Repo $Repo -Pr $Number -ConfigPath $ConfigPath
  if ($LASTEXITCODE -ne 0) { throw "AI Review evaluator failed for $Repo PR #$Number." }
}
function Get-CheckRun {
  param([string]$Head,[string]$Name)
  $encoded = [uri]::EscapeDataString($Name)
  $raw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$Head/check-runs?check_name=$encoded" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $runs = (($raw -join "`n") | ConvertFrom-Json).check_runs
  $latest = @($runs | Where-Object { $_.name -eq $Name -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
  if ($latest.Count -eq 0) { return $null }
  return $latest[0]
}
function Get-CheckConclusion { param([string]$Head,[string]$Name) $run=Get-CheckRun $Head $Name; if(-not$run){return $null}; return [string]$run.conclusion }
function Test-HeadDispatchEvidence {
  param([string]$Head)
  $run=Get-CheckRun $Head 'Advisory: AI Review'
  if(-not $run){return $false}
  return Test-CurrentDispatchEvidence -Summary ([string]$run.output.summary) -PolicyVersion ([int]$reviewPolicy.dispatch_policy_version)
}
function Get-FirstReviewRequestTime {
  param([int]$Number,[string]$Head)
  $requests = @(Get-Comments $Number | Where-Object { (Test-TrustedAutomationComment $_ ([string]$config.owner)) -and [string]$_.body -match "ai-review-request:(?:v\d+:)?(?:codex|copilot):$Head" } | Sort-Object created_at)
  if ($requests.Count -eq 0) { return $null }
  return [datetimeoffset]$requests[0].created_at
}

function Ensure-PrState {
  param([int]$Number)
  Remove-ForbiddenReviewers $Number
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN') { return $prData }
  $labels = @($prData.labels | ForEach-Object { $_.name })
  if ($prData.isDraft) {
    $draftAuthor = [string]$prData.author.login
    if ([bool]$automation.external_draft_promotion -and $draftAuthor -ne [string]$config.owner -and $draftAuthor -notin @('github-actions[bot]','github-actions')) {
      # External agents (dependabot, copilot agents, ...) open drafts by platform
      # behavior; promotion needs the dedicated automation identity, never a human.
      if ([string]::IsNullOrWhiteSpace($env:GH_TOKEN_ADMIN)) {
        Write-Host 'PROMOTION-BLOCKED: automation-identity-missing'
        Set-Blocked $Number 'automation-identity-missing' 'External draft promotion requires the dedicated automation identity (GH_TOKEN_ADMIN); it is not configured. Fail closed until the owner provisions it.' $prData
        return $prData
      }
      & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'promote-external-draft.ps1') -Repo $Repo -Pr $Number
      if ($LASTEXITCODE -ne 0) { throw "External draft promotion failed for $Repo PR #$Number." }
      return $prData
    }
    Set-Blocked $Number 'draft-pr' 'Ready-at-creation policy violation. Agents must create pull requests with draft:false; gh callers must omit --draft.' $prData
    throw "Ready-at-creation policy violation: $Repo PR #$Number is draft."
  }
  foreach ($readyCode in @('draft-pr','automation-identity-missing')) { Resolve-Block $Number $readyCode 'The pull request is Ready.' $prData }
  if ([string]$prData.author.login -eq 'Copilot' -or [string]$prData.headRefName -like 'copilot/*') {
    Set-Blocked $Number 'copilot-owned-pr' 'GitHub requires human review and merge for pull requests created by Copilot cloud agent. Use Copilot only on an existing non-Copilot PR, or re-home this work through a non-Copilot implementation lane.' $prData
    return $prData
  }
  if ($prData.mergeable -eq 'CONFLICTING') { Disable-AutoMerge $Number $prData; Request-Repair conflict $Number $prData; return $prData }
  foreach ($conflictCode in @('conflict-budget','conflict-dispatch-disabled')) { Resolve-Block $Number $conflictCode 'The current head is no longer conflicting.' $prData }
  try { $risk=Get-Risk $prData; Resolve-Block $Number 'risk-labels' "Risk labels now resolve unambiguously to $risk." $prData }
  catch { Set-Blocked $Number 'risk-labels' $_.Exception.Message $prData; return $prData }
  if ($risk -eq 'R4') { Disable-AutoMerge $Number $prData; Tag-Authority $Number R4; return $prData }
  if (Test-ControlPlane $Number) { Disable-AutoMerge $Number $prData; Tag-Authority $Number control_plane; return $prData }
  $labels = @((Get-Pr $Number).labels | ForEach-Object { $_.name })
  $activeBlocks = @(Get-ActiveBlockCodes $Number)
  if ($labels -contains $automation.blocked_label -and $activeBlocks.Count -eq 0) { Disable-AutoMerge $Number $prData; return $prData }
  if ($activeBlocks.Count -gt 0 -and @($activeBlocks | Where-Object { $_ -ne 'auto-merge-settings' }).Count -gt 0) { Disable-AutoMerge $Number $prData; return $prData }
  if (-not $prData.autoMergeRequest) {
    # Merge ordering: arm only after the exact head carries a PR Gate success and
    # a dispatch-appropriate AI Review conclusion; earlier events simply wait.
    $head = [string]$prData.headRefOid
    if ((Get-CheckConclusion $head ([string]$config.required_status_context)) -ne 'success') { return $prData }
    # Evaluated, not obeyed: current-policy-version advisory evidence must EXIST;
    # only a failure conclusion carrying a structured threat verdict refuses.
    # neutral and success both arm in every dispatch mode.
    $reviewRun = Get-CheckRun $head 'Advisory: AI Review'
    if (-not $reviewRun -or -not (Test-CurrentDispatchEvidence -Summary ([string]$reviewRun.output.summary) -PolicyVersion ([int]$reviewPolicy.dispatch_policy_version))) { return $prData }
    if ([string]$reviewRun.conclusion -eq 'failure' -and (Test-BlockingAiReviewBody ([string]$reviewRun.output.summary))) { return $prData }
    $armOutput = @(& pwsh -NoProfile -File (Join-Path $PSScriptRoot 'auto-merge.ps1') -Repo $Repo -Pr $Number -Risk $risk 2>&1 | ForEach-Object { [string]$_ })
    $armOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
      # RC-I: a script failure must never masquerade as a bare policy refusal —
      # the block quotes the underlying error line.
      $armError = [string](@($armOutput | ForEach-Object { ($_ -replace "`e\[[0-9;]*m",'').Trim() } | Where-Object { $_ }) | Select-Object -Last 1)
      Set-Blocked $Number 'auto-merge-settings' "Auto-merge could not be armed. Underlying error: $armError" $prData; return $prData
    }
    $prData = Get-Pr $Number
    Resolve-Block $Number 'auto-merge-settings' 'Live settings and ruleset now allow GitHub auto-merge to be armed.' $prData
  }
  return $prData
}

function Wait-ForReview {
  param([int]$Number,[string]$Head,[int]$Minutes)
  $deadline=[datetimeoffset]::UtcNow.AddMinutes($Minutes)
  do {
    Start-Sleep -Seconds ([int]$reviewPolicy.poll_seconds)
    $current=Get-Pr $Number
    if($current.state-ne'OPEN'-or$current.isDraft-or[string]$current.headRefOid-ne$Head){return 'changed'}
    Invoke-AiReview $Number
    if(@(Get-ReviewFailures $Number $current).Count-gt 0){return 'failed'}
    if(Test-AiReviewPassingConclusion (Get-CheckConclusion $Head 'Advisory: AI Review')){return 'success'}
  } while([datetimeoffset]::UtcNow-lt$deadline)
  return 'timeout'
}
function Resolve-ReviewBlocks {
  param([int]$Number,$PrData)
  foreach($code in @('review-request','review-fallback','review-timeout','review-budget')){Resolve-Block $Number $code 'Exact-head AI Review is now successful.' $PrData}
}
function Complete-ReviewSuccess {
  param([int]$Number)
  $current=Get-Pr $Number
  Resolve-ReviewBlocks $Number $current
  Ensure-PrState $Number | Out-Null
}

function Run-ReviewCycle {
  param([int]$Number)
  $prData=Get-Pr $Number
  if($prData.state-ne'OPEN'-or$prData.isDraft){return}
  # Evaluation is unconditional: every head gets an exact-head AI Review
  # conclusion in every dispatch_mode and solicit_reviews combination (the
  # disabled_pending_e2e canary dispatches nothing; enabled without solicitation
  # evaluates existing evidence only). Stale policy_version evidence is
  # re-evaluated so a dispatch_policy_version bump invalidates every open neutral.
  $head=[string]$prData.headRefOid
  if(-not((Test-AiReviewPassingConclusion (Get-CheckConclusion $head 'Advisory: AI Review'))-and(Test-HeadDispatchEvidence $head))){Invoke-AiReview $Number}
  if(@(Get-ReviewFailures $Number $prData).Count-gt 0){return}
  if(-not $reviewSolicit -or [string]$reviewPolicy.dispatch_mode-eq'disabled_pending_e2e'){Complete-ReviewSuccess $Number;return}
  # A neutral (awaiting-review) conclusion is passing but must not suppress
  # solicitation: request first (self-deduping), then complete on the verdict.
  $requestOutput=@(& pwsh -NoProfile -File (Join-Path $PSScriptRoot 'request-machine-review.ps1') -Repo $Repo -Pr $Number -Provider auto -ConfigPath $ConfigPath 2>&1|ForEach-Object{[string]$_})
  $requestOutput|Out-Host
  if($LASTEXITCODE-ne 0){
    $requestError=[string](@($requestOutput|ForEach-Object{($_ -replace "`e\[[0-9;]*m",'').Trim()}|Where-Object{$_})|Select-Object -Last 1)
    if($reviewRequired){Set-Blocked $Number 'review-request' "No budgeted machine reviewer could be requested. Underlying error: $requestError" $prData;return}
    Complete-ReviewSuccess $Number;return
  }
  if($reviewRequired){
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'pause-pending-review.ps1') -Repo $Repo -Pr $Number
    if($LASTEXITCODE-ne 0){throw'Could not pause auto-merge while machine review is pending.'}
  }

  $result=Wait-ForReview $Number ([string]$prData.headRefOid) ([int]$reviewPolicy.primary_wait_minutes)
  if($result-eq'success'){Complete-ReviewSuccess $Number;return}
  if($result-ne'timeout'){return}

  Invoke-AiReview $Number
  if(Test-AiReviewPassingConclusion (Get-CheckConclusion ([string]$prData.headRefOid) 'Advisory: AI Review')){Complete-ReviewSuccess $Number;return}
  if(@(Get-ReviewFailures $Number (Get-Pr $Number)).Count-gt 0){return}

  $fallbackOutput=@(& pwsh -NoProfile -File (Join-Path $PSScriptRoot 'request-machine-review.ps1') -Repo $Repo -Pr $Number -Provider auto -ConfigPath $ConfigPath 2>&1|ForEach-Object{[string]$_})
  $fallbackOutput|Out-Host
  if($LASTEXITCODE-ne 0){
    $fallbackError=[string](@($fallbackOutput|ForEach-Object{($_ -replace "`e\[[0-9;]*m",'').Trim()}|Where-Object{$_})|Select-Object -Last 1)
    if($reviewRequired){Set-Blocked $Number 'review-fallback' "Primary machine review stalled and no fallback reviewer was available. Underlying error: $fallbackError" $prData}
    return
  }
  $result=Wait-ForReview $Number ([string]$prData.headRefOid) ([int]$reviewPolicy.fallback_wait_minutes)
  if($result-eq'success'){Complete-ReviewSuccess $Number}
}
function Resolve-GateBlocks {
  param([int]$Number,$PrData)
  foreach($code in @('ci-budget','ci-dispatch-disabled','workflow-approval','gate-skipped','missing-pr-gate')){Resolve-Block $Number $code 'The current head now has a successful PR Gate.' $PrData}
}
function Handle-GateResult {
  param([int]$Number)
  $prData=Get-Pr $Number
  if($prData.state-ne'OPEN'-or$prData.isDraft){return}
  if($GateHeadSha-and[string]$prData.headRefOid-ne$GateHeadSha){return}
  if($GateConclusion-eq'success'){Resolve-GateBlocks $Number $prData;$prData=Ensure-PrState $Number;if(@(Get-ActiveBlockCodes $Number).Count-eq 0){Run-ReviewCycle $Number};return}
  $prData=Ensure-PrState $Number
  switch($GateConclusion){
    'failure'{Request-Repair ci $Number $prData $GateRunId}
    'timed_out'{Request-Repair ci $Number $prData $GateRunId}
    'startup_failure'{Request-Repair ci $Number $prData $GateRunId}
    'action_required'{Set-Blocked $Number 'workflow-approval' 'GitHub is waiting for workflow approval. Disable the Copilot cloud-agent workflow-approval setting for this repository.' $prData}
    'skipped'{Set-Blocked $Number 'gate-skipped' 'Ready PR Gate was skipped; its workflow trigger or job condition is invalid.' $prData}
    default{}
  }
}
function Handle-ReviewEvent {
  param([int]$Number)
  Remove-ForbiddenReviewers $Number
  $prData=Get-Pr $Number
  if($prData.state-ne'OPEN'-or$prData.isDraft){return}
  Invoke-AiReview $Number
  if(@(Get-ReviewFailures $Number $prData).Count-gt 0){return}
  if(Test-AiReviewPassingConclusion (Get-CheckConclusion ([string]$prData.headRefOid) 'Advisory: AI Review')){Complete-ReviewSuccess $Number}
}
function Handle-Watchdog {
  # Paginate every open PR: a capped list silently strands PRs past the cap.
  foreach($item in @(Get-Paged "repos/$Repo/pulls?state=open&per_page=100")){
    $number=[int]$item.number
    try{
      if(Deny-ForkPr $number){continue}
      $prData=Ensure-PrState $number
      if($prData.state-ne'OPEN'-or$prData.isDraft){continue}
      $head=[string]$prData.headRefOid
      $gate=Get-CheckConclusion $head ([string]$config.required_status_context)
      if($gate-eq'success'){
        Resolve-GateBlocks $number $prData
        if(-not $reviewSolicit -or $dispatchDisabled){Run-ReviewCycle $number;continue}
        Invoke-AiReview $number
        if(Test-AiReviewPassingConclusion (Get-CheckConclusion $head 'Advisory: AI Review')){Complete-ReviewSuccess $number;continue}
        $requestTime=Get-FirstReviewRequestTime $number $head
        if($requestTime-and([datetimeoffset]::UtcNow-$requestTime).TotalMinutes-ge[int]$reviewPolicy.absolute_timeout_minutes){if($reviewRequired){Set-Blocked $number 'review-timeout' "Machine review exceeded the absolute $($reviewPolicy.absolute_timeout_minutes)-minute timeout." $prData}}
        else{Run-ReviewCycle $number}
      } elseif($gate-in@('failure','timed_out','startup_failure')){Request-Repair ci $number $prData}
      elseif(-not$gate){Set-Blocked $number 'missing-pr-gate' 'No current-head PR Gate check exists.' $prData}
    } catch { Write-Warning "$Repo PR #$number watchdog: $($_.Exception.Message)" }
  }
}

switch($Mode){
  'pr-event'{if($Pr-le 0){throw'Pr is required.'};if(Deny-ForkPr $Pr){exit 0};Ensure-PrState $Pr|Out-Null}
  'gate-result'{if($Pr-le 0){throw'Pr is required.'};if(Deny-ForkPr $Pr){exit 0};Handle-GateResult $Pr}
  'review-event'{if($Pr-le 0){throw'Pr is required.'};if(Deny-ForkPr $Pr){exit 0};Handle-ReviewEvent $Pr}
  'comment-event'{if($Pr-le 0){throw'Pr is required.'};if(Deny-ForkPr $Pr){exit 0};Handle-ReviewEvent $Pr}
  'watchdog'{Handle-Watchdog}
}
